"""Live Telegram identities (PRODUCT §2.2, BUILD §5.4).

The registry lives outside AppState: a scenario reset keeps identities, profiles and opt-outs, while each new
world gets fresh donor records with no scenario history. A server restart clears it. The registry only records
who is who; the planner alone decides who is invited.
"""

import math
import random
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from rakt import store
from rakt.models import Channel, Contact, Donor, DonorProfile, RequestStatus
from rakt.domain.geo import EARTH_RADIUS_KM
from rakt.sim.world import AREAS, renamed

OPEN = {RequestStatus.OPEN, RequestStatus.COVERED, RequestStatus.SECURED}
COORDINATOR_SIM = Contact(name="Coordinator", channel=Channel.SIM, phone="coordinator")
JITTER_KM = 0.3

# S2 demo templates: O+, apheresis-capable, eligible, within ~2 km of Centre B (Jayanagar). Reused round-robin.
TEMPLATES = [
    DonorProfile(group="O_POS", area="Jayanagar", sex="M", age=28, weight_kg=70, apheresis_ok=True,
                 last_donation="never", lat=12.9305, lon=77.5850),
    DonorProfile(group="O_POS", area="Jayanagar", sex="F", age=31, weight_kg=62, apheresis_ok=True,
                 last_donation="over_4_months", lat=12.9268, lon=77.5806),
    DonorProfile(group="O_POS", area="Basavanagudi", sex="M", age=35, weight_kg=76, apheresis_ok=True,
                 last_donation="never", lat=12.9372, lon=77.5781),
    DonorProfile(group="O_POS", area="Jayanagar", sex="F", age=26, weight_kg=60, apheresis_ok=True,
                 last_donation="never", lat=12.9222, lon=77.5874),
    DonorProfile(group="O_POS", area="BTM Layout", sex="M", age=38, weight_kg=68, apheresis_ok=True,
                 last_donation="over_4_months", lat=12.9215, lon=77.5952),
    DonorProfile(group="O_POS", area="Jayanagar", sex="M", age=30, weight_kg=73, apheresis_ok=True,
                 last_donation="never", lat=12.9336, lon=77.5899),
]
LAST_DONATION_DAYS = {"never": None, "over_4_months": 150, "recent": 30}


@dataclass
class Identity:
    chat_id: str
    name: str
    role: str = "none"  # "donor" | "staff" | "family" | "coord" | "none": one role per chat
    profile: DonorProfile | None = None
    donor_id: str | None = None
    centre_id: str | None = None
    opted_out: bool = False


@dataclass
class Registry:
    identities: dict[str, Identity] = field(default_factory=dict)
    next_template: int = 0
    donor_seq: int = 0


registry = Registry()


def clear() -> None:
    """Forget everyone (tests; a server restart does the same)."""
    global registry
    registry = Registry()


def identity(chat_id: str, name: str) -> Identity:
    found = registry.identities.get(chat_id)
    if found is None:
        found = registry.identities[chat_id] = Identity(chat_id=chat_id, name=name)
    return found


def scenario_running() -> bool:
    state = store.state
    return state is not None and any(r.status in OPEN for r in state.main.requests.values())


# --- Donors ---

def donor_record(person: Identity, now: datetime) -> Donor:
    """A donor built from the profile, with no scenario history (no invites, deferrals or donations here)."""
    profile = person.profile
    lat, lon = (profile.lat, profile.lon) if profile.lat is not None else AREAS[profile.area]
    rng = random.Random(f"live:{person.chat_id}")
    deg = math.degrees(JITTER_KM / EARTH_RADIUS_KM)
    days = LAST_DONATION_DAYS[profile.last_donation]
    return Donor(
        id=person.donor_id, display_name=person.name, group=profile.group, sex=profile.sex, age=profile.age,
        weight_kg=profile.weight_kg, lat=round(lat + rng.uniform(-deg, deg), 5), lon=round(lon + rng.uniform(-deg, deg), 5),
        area=profile.area, contact=Contact(name=person.name, channel=Channel.TELEGRAM, chat_id=person.chat_id),
        opted_out=person.opted_out, apheresis_ok=profile.apheresis_ok,
        last_whole_blood_at=now - timedelta(days=days) if days else None, telegram_demo=True,
    )


def register_donor(chat_id: str, name: str, profile: DonorProfile) -> str:
    """Both onboarding routes end here. Same chat → same donor id. Joining mid-scenario adds the donor to the
    running pool without a replan: the planner considers them from its next wave."""
    person = identity(chat_id, name)
    if person.role == "staff":
        unlink_staff(person)
    person.role, person.profile, person.name = "donor", profile, name
    person.opted_out = False  # joining or finishing the Q&A is a fresh opt-in; STOP otherwise lasts across resets
    if person.donor_id is None:
        registry.donor_seq += 1
        person.donor_id = f"tg_{registry.donor_seq}"
    state = store.state
    if state is not None:
        s = state.main
        fresh = donor_record(person, state.clock.now)
        existing = s.donors.get(person.donor_id)
        if existing is not None:  # same person, new answers: keep this scenario's history
            fresh = fresh.model_copy(update={"invites": existing.invites, "deferred_until": existing.deferred_until,
                                             "apheresis_dates": existing.apheresis_dates,
                                             "last_whole_blood_at": existing.last_whole_blood_at or fresh.last_whole_blood_at})
        s.donors[person.donor_id] = named_apart(fresh, s.donors)
    return person.donor_id


def join_demo(chat_id: str, name: str) -> tuple[str, bool]:
    """(donor id, resumed). A donor who already has a profile keeps it; otherwise the next S2 template."""
    person = registry.identities.get(chat_id)
    if person is not None and person.role == "donor" and person.profile is not None:
        return register_donor(chat_id, name, person.profile), True
    template = TEMPLATES[registry.next_template % len(TEMPLATES)]
    registry.next_template += 1
    return register_donor(chat_id, name, template), False


def forget_donor(chat_id: str) -> str | None:
    """/reset: drop this chat's donor association and profile; returns the old donor id (None if there was none).
    STOP stays as it was; the next join or finished profile gets a fresh donor id."""
    person = registry.identities.get(chat_id)
    if person is None or person.role != "donor":
        return None
    old = person.donor_id
    person.role, person.profile, person.donor_id = "none", None, None
    return old


def release_staff(chat_id: str) -> str | None:
    """Staff /reset: drop this chat's centre link (the centre itself, its stock and everyone else stay as they are).
    Returns the centre id, or None if the chat isn't staff."""
    person = registry.identities.get(chat_id)
    if person is None or person.role != "staff":
        return None
    centre_id = person.centre_id
    unlink_staff(person)
    person.role = "none"
    return centre_id


def opt_out(chat_id: str) -> None:
    """STOP: kept across scenario resets for the life of the process."""
    person = registry.identities.get(chat_id)
    if person is not None:
        person.opted_out = True
    state = store.state
    if state is not None and person is not None and person.donor_id in state.main.donors:
        state.main.donors[person.donor_id].opted_out = True


# --- Staff, family, coordinator ---

def staff_contact(centre_name: str, person: Identity) -> Contact:
    return Contact(name=f"{centre_name} staff", channel=Channel.TELEGRAM, chat_id=person.chat_id)


def unlink_staff(person: Identity) -> None:
    state = store.state
    if state is not None and person.centre_id in state.main.centres:
        centre = state.main.centres[person.centre_id]
        centre.contact = Contact(name=f"{centre.name} staff", channel=Channel.SIM, phone=centre.id)
    person.centre_id = None


def detach_donor(person: Identity) -> None:
    """A chat that becomes staff/family/coordinator leaves the donor pool (its record stays for history)."""
    state = store.state
    if state is not None and person.donor_id in state.main.donors:
        state.main.donors[person.donor_id].consent = False


def link_chat(start_param: str, chat_id: str, display_name: str) -> str:
    """staff_<centre_id> | family | coord, in a private chat. Returns the bot's reply."""
    person = identity(chat_id, display_name)
    state = store.state
    if person.role == "staff" and state is not None and person.centre_id in state.main.centres:
        current = state.main.centres[person.centre_id]
        if start_param == f"staff_{person.centre_id}":
            return f"You're already linked as {current.name} staff."
        return f"You're linked as {current.name} staff. Send /reset to release it first."
    if start_param.startswith("staff_"):
        centre_id = start_param.removeprefix("staff_")
        if state is None or centre_id not in state.main.centres:
            return "That centre link isn't valid."
        centre = state.main.centres[centre_id]
        holder = next((o for o in registry.identities.values()
                       if o.role == "staff" and o.centre_id == centre_id and o is not person), None)
        if holder is not None:  # one staff chat per centre, and never a silent takeover
            return f"{centre.name} already has a linked staff account. Ask them to send /reset first."
        detach_donor(person)
        person.role, person.centre_id = "staff", centre_id
        centre.contact = staff_contact(centre.name, person)
        return f"You're linked as {centre.name} staff. Cards for this centre will come here. Send /reset to release it."
    if start_param in ("family", "coord"):
        detach_donor(person)
        for other in registry.identities.values():
            if other.role == start_param and other is not person:
                other.role = "none"
        person.role = start_param
        if start_param == "family":
            apply_family(person)
            return "You're linked as the family contact for the demo request."
        return "You're linked as the coordinator. Alerts will come here."
    return "Unknown link."


def family_chat() -> Identity | None:
    return next((p for p in registry.identities.values() if p.role == "family"), None)


def apply_family(person: Identity) -> None:
    state = store.state
    if state is None:
        return
    for request in state.main.requests.values():
        if request.family is not None and request.status in OPEN:
            request.family = Contact(name="Family", channel=Channel.TELEGRAM, chat_id=person.chat_id)


def coordinator_contact() -> Contact:
    person = next((p for p in registry.identities.values() if p.role == "coord"), None)
    if person is None:
        return COORDINATOR_SIM
    return Contact(name="Coordinator", channel=Channel.TELEGRAM, chat_id=person.chat_id)


def named_apart(donor: Donor, donors: dict[str, Donor]) -> Donor:
    """A Telegram name that matches another donor's gets a marker, so the two are never confused on screen."""
    if any(other.display_name == donor.display_name for other_id, other in donors.items() if other_id != donor.id):
        return renamed(donor, f"{donor.display_name} · Telegram")
    return donor


# --- A new world ---

def attach(state) -> None:
    """After a scenario (re)load: every linked donor joins the rakttrace lane with a fresh record (the today's-workflow
    lane never messages real people); staff and family links are re-applied."""
    s = state.main
    for person in registry.identities.values():
        if person.role == "donor" and person.profile is not None:
            s.donors[person.donor_id] = named_apart(donor_record(person, state.clock.now), s.donors)
        elif person.role == "staff" and person.centre_id in s.centres:
            centre = s.centres[person.centre_id]
            centre.contact = staff_contact(centre.name, person)
    family = family_chat()
    if family is not None:
        apply_family(family)

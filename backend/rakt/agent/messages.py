"""Message copy (PRODUCT §5). Channels only deliver what is rendered here."""

from datetime import datetime

from rakt.models import (
    GROUP_LABELS, PRODUCT_LABELS, Button, Centre, Contact, Donor, Hospital, Outgoing, Pledge, Request, Reservation,
)


def when(at: datetime) -> str:
    return at.strftime("%H:%M, %d %b")


# --- Staff: stock ---

def staff_hold(request: Request, res: Reservation, centre: Centre, hospital: Hospital) -> Outgoing:
    body = (f"RaktTrace · {request.id}: can you reserve {res.units_asked} unit(s) of {GROUP_LABELS[res.group]} "
            f"{PRODUCT_LABELS[request.product]} for a patient at {hospital.name}, needed by {when(request.deadline_at)}?")
    buttons = [
        Button(id=f"R:{res.id}:ALL", title=f"Reserve {res.units_asked}"),
        Button(id=f"R:{res.id}:SOME", title="Some"),
        Button(id=f"R:{res.id}:NONE", title="None"),
    ]
    return Outgoing(to=centre.contact, kind="staff_hold", body=body, buttons=buttons, request_id=request.id)


def staff_hold_count(request: Request, res: Reservation, centre: Centre) -> Outgoing:
    """After "Some": pick how many (button ids N{k}, BUILD §5.3)."""
    counts = range(1, max(res.units_asked, 2))
    buttons = [Button(id=f"R:{res.id}:N{k}", title=str(k)) for k in counts]
    return Outgoing(to=centre.contact, kind="staff_hold_count", body=f"{request.id}: how many units can you reserve?",
                    buttons=buttons, request_id=request.id)


def staff_release(request: Request, centre: Centre) -> Outgoing:
    return Outgoing(to=centre.contact, kind="staff_release",
                    body=f"{request.id}: the reservation is no longer needed. Thank you!", request_id=request.id)


# --- Staff: donor visit ---

def staff_incoming(request: Request, pledge: Pledge, donor: Donor, centre: Centre, hospital: Hospital,
                   eta: datetime) -> Outgoing:
    body = (f"🩸 Incoming donor · {request.id}\n"
            f"{donor.display_name} · {GROUP_LABELS[donor.group]} · Booking code {pledge.booking_code}\n"
            f"For: {PRODUCT_LABELS[request.product]}, {hospital.name}, needed by {when(request.deadline_at)}\n"
            f"Expected around {when(eta)}")
    buttons = [Button(id=f"V:{pledge.id}:ARRIVED", title="Arrived"),
               Button(id=f"V:{pledge.id}:NOSHOW", title="Didn't show")]
    return Outgoing(to=centre.contact, kind="staff_incoming", body=body, buttons=buttons, request_id=request.id)


def staff_visit(request: Request, pledge: Pledge, donor: Donor, centre: Centre) -> Outgoing:
    buttons = [Button(id=f"V:{pledge.id}:COLLECTED", title="Collected"),
               Button(id=f"V:{pledge.id}:DEFERRED", title="Deferred")]
    return Outgoing(to=centre.contact, kind="staff_visit",
                    body=f"{donor.display_name} · code {pledge.booking_code} · screening", buttons=buttons,
                    request_id=request.id)


# --- Donor ---

def donor_invite(request: Request, pledge: Pledge, donor: Donor, centre: Centre, km: float,
                 latest_arrival: datetime) -> Outgoing:
    body = (f"🩸 RaktTrace · {request.id}\n"
            f"{GROUP_LABELS[request.group]} {PRODUCT_LABELS[request.product]} needed at {centre.name}, {centre.area}, "
            f"by {when(request.deadline_at)}.\n"
            f"You're a match, about {km:.1f} km away. Can you reach {centre.name} by {when(latest_arrival)}?\n"
            "Only come if you're well (no recent illness, tattoo or antibiotics). Staff at the centre will check you.")
    buttons = [Button(id=f"P:{pledge.id}:YES", title="Yes, I can go"),
               Button(id=f"P:{pledge.id}:NO", title="Not this time"),
               Button(id=f"P:{pledge.id}:STOP", title="Stop requests")]
    return Outgoing(to=donor.contact, kind="donor_invite", body=body, buttons=buttons, request_id=request.id)


def donor_go(request: Request, pledge: Pledge, donor: Donor, centre: Centre, latest_arrival: datetime) -> Outgoing:
    body = (f"Thank you! 🙏 Please go to {centre.name}, {centre.address}.\n"
            f"Map: https://maps.google.com/?q={centre.lat},{centre.lon}\n"
            f"Booking code: {pledge.booking_code}. Show it at the counter.\n"
            f"Please arrive by {when(latest_arrival)}.")
    buttons = [Button(id=f"P:{pledge.id}:OMW", title="On my way"),
               Button(id=f"P:{pledge.id}:CANT", title="Can't make it")]
    return Outgoing(to=donor.contact, kind="donor_go", body=body, buttons=buttons, request_id=request.id)


def donor_standby(request: Request, pledge: Pledge, donor: Donor, standby_until: datetime) -> Outgoing:
    body = (f"Thank you! Enough donors are heading there right now. Please stay on standby until "
            f"{when(standby_until)}. We'll message only if we need you.")
    buttons = [Button(id=f"P:{pledge.id}:OK", title="OK"), Button(id=f"P:{pledge.id}:CANT", title="Not available")]
    return Outgoing(to=donor.contact, kind="donor_standby", body=body, buttons=buttons, request_id=request.id)


def donor_promote(request: Request, pledge: Pledge, donor: Donor, centre: Centre, latest_arrival: datetime) -> Outgoing:
    buttons = [Button(id=f"P:{pledge.id}:OMW", title="Going now"), Button(id=f"P:{pledge.id}:CANT", title="Can't")]
    return Outgoing(to=donor.contact, kind="donor_promote", buttons=buttons, request_id=request.id,
                    body=f"{request.id}: we need you now. Can you reach {centre.name} by {when(latest_arrival)}?")


def donor_text(kind: str, request: Request, donor: Donor, **fields) -> Outgoing:
    """Donor messages without buttons."""
    bodies = {
        "donor_too_late": "Thank you! This one is needed by {deadline}, so a donation at that time would be too late. "
                          "We'll ask you next time.",
        "donor_thanks_no": "No problem, thank you for replying.",
        "donor_not_needed": "Thank you! Enough donors are already lined up for {code}, so you're not needed this time. "
                            "Stay rested for the next one 💙",
        "donor_thanks_collected": "Thank you for donating today ❤️ You can donate again from {next_date}.",
        "donor_unclear": "Sorry, I didn't get that. Please tap one of the buttons above 🙏",
        "donor_stand_down": "Blood for {code} is arranged. You're not needed this time and stay rested for the next one. "
                            "Thank you 💙",
        "donor_closed": "{code} is closed, so you're not needed for it any more. Thank you for being ready 💙",
    }
    body = bodies[kind].format(code=request.id, deadline=when(request.deadline_at), **fields)
    return Outgoing(to=donor.contact, kind=kind, body=body, request_id=request.id)


# --- Staff: ready for the patient ---

def ready_buttons(target: str, target_id: str) -> list[Button]:
    """target "P" (a donor's unit) or "R" (reserved stock)."""
    return [Button(id=f"D:{target}:{target_id}:READY", title="Ready for patient"),
            Button(id=f"D:{target}:{target_id}:FAILED", title="Failed testing")]


def staff_ready(request: Request, centre: Centre, target: str, target_id: str, booking_code: str | None) -> Outgoing:
    unit = f"Unit from code {booking_code}" if booking_code else "Unit from reserved stock"
    return Outgoing(to=centre.contact, kind="staff_ready", buttons=ready_buttons(target, target_id),
                    body=f"{unit} for {request.id}: ready for the patient?", request_id=request.id)


def staff_reminder(request: Request, centre: Centre, subject: str, buttons: list[Button]) -> Outgoing:
    return Outgoing(to=centre.contact, kind="staff_reminder", buttons=buttons,
                    body=f"Reminder · {request.id}: any update on {subject}?", request_id=request.id)


# --- Family and coordinator ---

def family_secured(request: Request, centres: list[str], ready_by: datetime) -> Outgoing:
    body = (f"✅ Blood for {request.id} is arranged at {' and '.join(centres)}, ready by {when(ready_by)}. "
            "Please ask your groups to **stop forwarding** the message.")
    return Outgoing(to=request.family, kind="family_secured", body=body, request_id=request.id)


def family_fulfilled(request: Request, centres: list[str]) -> Outgoing:
    body = (f"✅ {request.units} unit(s) for {request.id} are ready for the patient at {' and '.join(centres)}. "
            "The hospital team will take it from here.")
    return Outgoing(to=request.family, kind="family_fulfilled", body=body, request_id=request.id)


def coord_alert(request: Request, to: Contact, p: float, brief: str, call_list: list[dict]) -> Outgoing:
    lines = [f"{i}) {c['centre']}, {c['phone']}, {c['note']}" for i, c in enumerate(call_list, start=1)]
    body = (f"⚠️ {request.id} needs attention. Chance of {request.units} unit(s) by {when(request.deadline_at)}: "
            f"{round(100 * p)}%.\n{brief}\nCall list:\n" + ("\n".join(lines) or "none listing compatible units"))
    return Outgoing(to=to, kind="coord_alert", body=body, request_id=request.id)


def coord_failed(request: Request, to: Contact, ready: int, summary: str) -> Outgoing:
    return Outgoing(to=to, kind="coord_failed", request_id=request.id,
                    body=f"{request.id}: deadline passed. Ready: {ready} of {request.units}. {summary}")

"""Gate 6.V, live identities (PRODUCT §2.2): onboarding, identity, reset, STOP, routing, planner integration.
The bot's logic is driven through its plain functions; nothing talks to Telegram."""

from rakt import store
from rakt.agent import live, loop, ranking
from rakt.channels import simulated, telegram_bot as bot
from rakt.models import PledgeStatus, RequestStatus
from rakt.sim import bots

S, Q = PledgeStatus, RequestStatus
JUDGE, OTHER, STAFF = "9001", "9002", "9003"


def reset(scenario_id: str):
    loop.reset_scenario(scenario_id)
    state = store.state
    (rid,) = state.main.requests
    return state, rid


def join(chat_id: str, name: str = "Judge A."):
    text, _ = bot.on_callback(chat_id, name, "O:JOIN")
    return live.registry.identities[chat_id].donor_id, text


def create(chat_id: str, answers: dict, name: str = "Judge B."):
    bot.on_callback(chat_id, name, "O:CREATE")
    reply = None
    for step, (field, _, _) in enumerate(bot.QUESTIONS):
        reply = bot.on_callback(chat_id, name, f"Q:{step}:{answers[field]}")
    return live.registry.identities[chat_id].donor_id, reply


def run_until(state, condition, limit=2000):
    for _ in range(limit):
        if condition() or state.clock.step(loop.on_timer) is None:
            return
    raise AssertionError("condition never met")


def run_all(state):
    while state.clock.step(loop.on_timer):
        pass


def pledge_of(state, donor_id):
    return next((p for p in state.main.pledges.values() if p.donor_id == donor_id), None)


def first_wave(state):
    run_until(state, lambda: bool(state.main.pledges))
    return list(state.main.pledges.values())


# --- Identity ---

def test_same_account_twice_is_one_identity():
    reset("s2_dengue_sdp")
    first, _ = join(JUDGE)
    again, text = join(JUDGE)
    assert first == again and len(live.registry.identities) == 1
    assert text.startswith("Welcome back")
    start_text, buttons = bot.on_start(JUDGE, "Judge A.", "", private=True)
    assert start_text.startswith("Welcome back") and [b.id for b in buttons] == ["O:JOIN", "O:CREATE"]


def test_templates_are_reused_not_a_cap():
    reset("s2_dengue_sdp")
    ids = [join(str(10_000 + i), f"Judge {i}")[0] for i in range(len(live.TEMPLATES) + 3)]
    assert len(set(ids)) == len(ids)  # everyone gets their own donor record
    assert all(store.state.main.donors[d].telegram_demo for d in ids)


def test_half_finished_qa_restarts_safely():
    reset("s2_dengue_sdp")
    bot.on_callback(OTHER, "B", "O:CREATE")
    bot.on_callback(OTHER, "B", "Q:0:O_POS")
    assert bot.on_text(OTHER, "hello")[0].startswith("Please tap")
    text, _ = bot.on_start(OTHER, "B", "", private=True)  # /start mid-Q&A
    assert OTHER not in bot._onboarding and not text.startswith("Welcome back")
    reply_text, buttons = bot.on_callback(OTHER, "B", "Q:4:70")  # a stale button
    assert reply_text.startswith("Let's start again") and buttons[0].id.startswith("Q:0:")
    assert OTHER not in live.registry.identities or live.registry.identities[OTHER].profile is None


def test_group_chats_are_not_linked():
    reset("s2_dengue_sdp")
    text, _ = bot.on_start(STAFF, "Aditya", "staff_c_b", private=False)
    assert "private chat" in text and STAFF not in live.registry.identities


# --- Reset, history, STOP ---

def test_reset_keeps_identity_and_profile_but_clears_history():
    state, rid = reset("s2_dengue_sdp")
    donor_id, _ = join(JUDGE)
    profile = live.registry.identities[JUDGE].profile
    first_wave(state)
    assert store.state.main.donors[donor_id].invites  # invited in this run

    state, rid = reset("s2_dengue_sdp")
    donor = state.main.donors[donor_id]
    assert live.registry.identities[JUDGE].profile == profile
    assert donor.invites == [] and donor.deferred_until is None
    assert pledge_of(state, donor_id) is None
    first_wave(state)
    assert pledge_of(state, donor_id) is not None  # no stale invite history, so rested and invited again


def test_stop_survives_reset_until_the_person_rejoins():
    reset("s2_dengue_sdp")
    donor_id, _ = join(JUDGE)
    bot.on_stop(JUDGE)
    state, _ = reset("s2_dengue_sdp")
    assert state.main.donors[donor_id].opted_out
    first_wave(state)
    assert pledge_of(state, donor_id) is None  # never invited while opted out
    join(JUDGE)  # an explicit re-join is a fresh opt-in
    assert not store.state.main.donors[donor_id].opted_out


def test_stop_reply_to_an_invite_persists():
    state, rid = reset("s2_dengue_sdp")
    donor_id, _ = join(JUDGE)
    first_wave(state)
    pledge = pledge_of(state, donor_id)
    bot.on_text(JUDGE, "STOP")
    assert pledge.status == S.OPTED_OUT and live.registry.identities[JUDGE].opted_out


# --- Planner integration ---

def test_template_donor_is_invited_by_normal_planner_decisions():
    state, rid = reset("s2_dengue_sdp")
    donor_id, _ = join(JUDGE)
    request = state.main.requests[rid]
    centre = state.main.centres["c_b"]
    candidates = ranking.candidates(state.main, request, centre, state.clock.now)
    assert candidates[0].donor_id == donor_id  # passes every filter; demo donors rank 2nd (after exact group)
    wave = first_wave(state)
    assert pledge_of(state, donor_id) in wave
    kinds = [m.kind for m in simulated.inbox(JUDGE)]
    assert kinds == ["donor_invite"]  # the bot is off in tests, so the message shows on the sim phone instead
    assert simulated.inbox(JUDGE)[0].channel == "sim"


def test_live_donors_never_get_simulated_replies():
    state, rid = reset("s2_dengue_sdp")
    donor_id, _ = join(JUDGE)
    first_wave(state)
    pledge = pledge_of(state, donor_id)
    assert bots.latent_for(pledge.id) is None
    assert not any(t.payload.get("sender_id") == donor_id for t in state.clock.pending() if t.kind == "sim_inbound")
    run_all(state)
    assert pledge.replied_at is None  # nobody answered on the judge's behalf


def test_live_donors_are_not_invited_in_s1_or_s3():
    for scenario in ("s1_surgery_tonight", "s3_no_way_in_time"):
        state, rid = reset(scenario)
        donor_id, _ = join(JUDGE)
        run_all(state)
        assert pledge_of(state, donor_id) is None
        assert state.main.pledges == {}


def test_mid_scenario_joiner_waits_for_the_next_wave():
    state, rid = reset("s2_dengue_sdp")
    first_wave(state)
    decisions, timers = len(state.main.decisions), len(state.clock.pending())
    donor_id, text = join(JUDGE)
    assert "You'll get a message only if" in text
    assert len(state.main.decisions) == decisions and len(state.clock.pending()) == timers  # no replan
    assert pledge_of(state, donor_id) is None
    run_until(state, lambda: any(p.wave == 2 for p in state.main.pledges.values()))
    second = [p for p in state.main.pledges.values() if p.wave == 2]
    assert pledge_of(state, donor_id) in second


def test_ineligible_custom_profile_is_never_invited():
    state, rid = reset("s2_dengue_sdp")
    over_60 = {"group": "O_POS", "area": "Jayanagar", "sex": "M", "age": "62", "weight_kg": "70",
               "last_donation": "never", "apheresis_ok": "yes"}
    donor_id, reply = create(OTHER, over_60)
    assert "synthetic" in reply[0]
    run_all(state)
    assert pledge_of(state, donor_id) is None  # apheresis age limit (E3), applied by the planner's filters


def test_custom_profile_is_registered_without_a_running_request():
    state, rid = reset("s1_surgery_tonight")
    run_all(state)  # S1 fulfilled: nothing open
    donor_id, reply = create(OTHER, {"group": "B_POS", "area": "Koramangala", "sex": "F", "age": "32",
                                     "weight_kg": "55", "last_donation": "over_4_months", "apheresis_ok": "no"})
    assert "No request is running" in reply[0] and donor_id in store.state.main.donors


def test_live_donor_reply_moves_the_request():
    state, rid = reset("s2_dengue_sdp")
    donor_id, _ = join(JUDGE)
    first_wave(state)
    pledge = pledge_of(state, donor_id)
    bot.on_text(JUDGE, "haan abhi aa sakta hoon")  # free text, rule reader (LLM off in tests)
    assert pledge.status == S.ACTIVE and pledge.booking_code
    assert [m.kind for m in simulated.inbox(JUDGE) if m.direction == "out"][-1] == "donor_go"


def test_live_donor_button_tap_reaches_the_loop():
    state, rid = reset("s2_dengue_sdp")
    donor_id, _ = join(JUDGE)
    first_wave(state)
    pledge = pledge_of(state, donor_id)
    assert bot.on_callback(JUDGE, "Judge A.", f"P:{pledge.id}:NO") is None
    assert pledge.status == S.DECLINED
    assert bot.on_callback(OTHER, "Someone", f"P:{pledge.id}:YES") is None  # another chat can't answer for them
    assert pledge.status == S.DECLINED


def test_today_lane_never_holds_live_donors():
    state, rid = reset("s2_dengue_sdp")
    donor_id, _ = join(JUDGE)
    assert donor_id in state.main.donors and donor_id not in state.lanes["today"].donors


# --- Roles ---

def test_switching_a_chat_to_staff_removes_it_from_the_donor_pool():
    state, rid = reset("s2_dengue_sdp")
    donor_id, _ = join(STAFF, "Aditya")
    text, _ = bot.on_start(STAFF, "Aditya", "staff_c_b", private=True)
    assert "Centre B staff" in text
    request, centre = state.main.requests[rid], state.main.centres["c_b"]
    assert centre.contact.chat_id == STAFF and centre.contact.channel == "telegram"
    assert donor_id not in [c.donor_id for c in ranking.candidates(state.main, request, centre, state.clock.now)]

    state, rid = reset("s2_dengue_sdp")  # the link survives a reset; the chat stays out of the pool
    assert state.main.centres["c_b"].contact.chat_id == STAFF and donor_id not in state.main.donors


def test_staff_taps_come_from_the_linked_chat_and_sim_staff_stand_aside():
    state, rid = reset("s2_dengue_sdp")
    bot.on_start(STAFF, "Aditya", "staff_c_b", private=True)
    run_until(state, lambda: any(p.status == S.ACTIVE for p in state.main.pledges.values()))
    active = next(p for p in state.main.pledges.values() if p.status == S.ACTIVE)
    assert not any(t.payload.get("sender_id") == "c_b" for t in state.clock.pending() if t.kind == "sim_inbound")
    bot.on_callback(OTHER, "Someone", f"V:{active.id}:ARRIVED")  # not Centre B's staff
    assert active.status == S.ACTIVE
    bot.on_callback(STAFF, "Aditya", f"V:{active.id}:ARRIVED")
    assert active.status == S.ARRIVED


def test_one_staff_chat_per_centre_newest_wins():
    reset("s2_dengue_sdp")
    bot.on_start(STAFF, "Aditya", "staff_c_b", private=True)
    bot.on_start(OTHER, "Backup", "staff_c_b", private=True)
    assert store.state.main.centres["c_b"].contact.chat_id == OTHER
    assert live.registry.identities[STAFF].role == "none"


def test_rejoining_as_donor_unlinks_staff():
    state, _ = reset("s2_dengue_sdp")
    bot.on_start(STAFF, "Aditya", "staff_c_b", private=True)
    join(STAFF, "Aditya")
    assert state.main.centres["c_b"].contact.channel == "sim" and live.registry.identities[STAFF].role == "donor"


def test_family_and_coordinator_links():
    state, rid = reset("s2_dengue_sdp")
    bot.on_start(OTHER, "Mum", "family", private=True)
    bot.on_start(STAFF, "Coord", "coord", private=True)
    assert state.main.requests[rid].family.chat_id == OTHER
    assert live.coordinator_contact().chat_id == STAFF
    state, rid = reset("s2_dengue_sdp")
    assert state.main.requests[rid].family.chat_id == OTHER  # re-applied after a reset


def test_unknown_staff_link():
    reset("s2_dengue_sdp")
    assert bot.on_start(STAFF, "X", "staff_c_zz", private=True)[0] == "That centre link isn't valid."
    assert STAFF not in live.registry.identities or live.registry.identities[STAFF].role == "none"

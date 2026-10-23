from datetime import datetime

from fastapi.testclient import TestClient

from rakt import llm, store
from rakt.agent import loop
from rakt.channels import router, simulated
from rakt.clock import Timer
from rakt.main import app
from rakt.models import IST, Button, Channel, Contact, Inbound, Message, Outgoing, PleaDraft, ReplyRead
from rakt.sim.scenarios import load_scenario


def test_health_200_and_default_scenario_loaded():
    with TestClient(app) as client:
        response = client.get("/api/health")
    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True and body["llm"] in ("on", "off") and body["telegram"] in ("ok", "off")
    assert datetime.fromisoformat(body["now"]).utcoffset() == IST.utcoffset(None)
    assert store.state.scenario is not None


def test_step_moves_the_clock():
    state = load_scenario("s1_surgery_tonight")
    start = state.clock.now
    state.clock.schedule(start.replace(minute=8), "staff_reply", payload={"centre_id": "c_a"})
    fired: list[Timer] = []
    state.clock.step(fired.append)
    assert state.clock.now > start and fired[0].kind == "staff_reply"


def test_router_delivers_to_sim_inbox():
    store.set_state(load_scenario("s2_dengue_sdp"))
    to = Contact(name="Centre B staff", channel=Channel.SIM, phone="c_b")
    message = router.deliver(Outgoing(to=to, kind="staff_hold", body="hold?", buttons=[Button(id="R:x:ALL", title="Reserve 1")]))
    assert isinstance(message, Message) and message.direction == "out"
    assert simulated.inbox("c_b") == [message]


def test_loop_stubs_accept_input():
    now = datetime(2026, 10, 24, 22, 40, tzinfo=IST)
    assert loop.handle_inbound(Inbound(channel=Channel.SIM, sender_id="d_001", text="haan", at=now)) is None
    assert isinstance(loop.link_chat("donor", "123", "Judge"), str)


def test_llm_stubs_return_rule_fallbacks():
    now = datetime(2026, 10, 24, 22, 40, tzinfo=IST)
    draft = llm.read_plea("O+ platelets kal 2 baje City General", [], now)
    assert isinstance(draft, PleaDraft) and draft.read_by == "rules"
    reply = llm.read_reply("haan", now, now)
    assert isinstance(reply, ReplyRead) and reply.read_by == "rules"
    assert isinstance(llm.write_brief({"status": "OPEN"}), str)
    before = llm.status()["enabled"]
    llm.set_enabled(False)
    assert llm.status()["enabled"] is False and set(llm.status()) == {"enabled", "chain"}
    llm.set_enabled(before)

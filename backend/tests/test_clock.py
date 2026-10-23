from datetime import datetime, timedelta

from rakt.clock import Clock
from rakt.models import IST

T0 = datetime(2026, 10, 24, 22, 0, tzinfo=IST)


def at(minutes: float) -> datetime:
    return T0 + timedelta(minutes=minutes)


def test_events_fire_in_time_order():
    clock = Clock(T0)
    for m, kind in [(30, "c"), (10, "a"), (20, "b"), (10, "a2")]:
        clock.schedule(at(m), kind)
    fired = clock.advance(60, lambda t: None)
    assert [t.kind for t in fired] == ["a", "a2", "b", "c"]
    assert clock.now == at(60)


def test_timers_scheduled_inside_a_jump_fire():
    clock = Clock(T0)
    clock.schedule(at(10), "first")

    def handler(timer):
        if timer.kind == "first":
            clock.schedule(at(25), "inside")
            clock.schedule(at(90), "outside")

    fired = clock.advance(60, handler)
    assert [t.kind for t in fired] == ["first", "inside"]
    assert [t.kind for t in clock.pending()] == ["outside"]


def test_handler_sees_event_time():
    clock = Clock(T0)
    clock.schedule(at(15), "x")
    seen = []
    clock.advance(60, lambda t: seen.append(clock.now))
    assert seen == [at(15)]


def test_step_processes_exactly_one_event():
    clock = Clock(T0)
    clock.schedule(at(5), "a")
    clock.schedule(at(40), "b")
    fired = []
    timer = clock.step(fired.append)
    assert timer.kind == "a" and fired == [timer]
    assert clock.now == at(5)
    assert [t.kind for t in clock.pending()] == ["b"]


def test_step_with_no_events_does_nothing():
    clock = Clock(T0)
    assert clock.step(lambda t: None) is None
    assert clock.now == T0


def test_cancelled_timer_never_fires():
    clock = Clock(T0)
    timer = clock.schedule(at(5), "a")
    clock.schedule(at(10), "b")
    clock.cancel(timer)
    fired = clock.advance(30, lambda t: None)
    assert [t.kind for t in fired] == ["b"]

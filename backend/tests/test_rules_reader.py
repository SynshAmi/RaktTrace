from datetime import datetime

import pytest

from rakt.llm import rules
from rakt.models import IST, Intent

NOW = datetime(2026, 10, 24, 22, 40, tzinfo=IST)


def read(text):
    return rules.read_reply(text, NOW, NOW)


@pytest.mark.parametrize("text, intent", [
    ("haan abhi aa sakta hoon", Intent.YES),
    ("Yes coming now", Intent.YES),
    ("OK", Intent.YES),
    ("हाँ", Intent.YES),
    ("nahi bhai busy", Intent.NO),
    ("not today", Intent.NO),
    ("नहीं", Intent.NO),
    ("STOP", Intent.STOP),
    ("band karo", Intent.STOP),
    ("haan but busy", Intent.UNCLEAR),  # both
    ("Where is the blood bank located?", Intent.UNCLEAR),  # neither
    ("", Intent.UNCLEAR),
])
def test_word_lists(text, intent):
    assert read(text).intent == intent
    assert read(text).read_by == "rules"


def test_whole_words_only():
    assert read("Not available sorry").intent == Intent.UNCLEAR  # "not" isn't "no"
    assert read("phone").intent == Intent.UNCLEAR


@pytest.mark.parametrize("text, hhmm", [
    ("kal 11:55 ke baad free hoon", "11:55"),
    ("kal subah 8 baje aa jaunga", "08:00"),
    ("I can come tomorrow morning at 9am", "09:00"),
    ("Can donate tomorrow after 10 AM", "10:00"),
    ("kal 2 baje", "14:00"),
    ("kal shaam 6 baje", "18:00"),
])
def test_tomorrow_plus_a_time_is_a_later_yes(text, hhmm):
    r = read(text)
    assert r.intent == Intent.YES
    assert r.available_from.strftime("%Y-%m-%d %H:%M") == f"2026-10-25 {hhmm}"


def test_tomorrow_time_with_a_no_word_is_unclear():
    assert read("Aaj possible nahi hai, kal subah 7 baje aa sakta hoon").intent == Intent.UNCLEAR


def test_now_yes_has_no_available_from():
    assert read("haan").available_from is None


def test_stop_wins():
    assert read("stop, nahi chahiye").intent == Intent.STOP

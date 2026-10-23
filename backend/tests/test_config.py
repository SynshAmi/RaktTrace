import re
from pathlib import Path

from rakt import config

AGENT_MD = Path(__file__).resolve().parents[2] / "docs" / "AGENT.md"

EXPECTED = {
    "TARGET_P": 0.90,
    "ESCALATE_P": 0.30,
    "HALFTIME_ESCALATE_P": 0.70,
    "DONOR_BURDEN_TAU": 0.015,
    "WAVE_CAP": 10,
    "WAVE_INTERVAL_MIN": 10,
    "REQUEST_DONOR_CAP": 30,
    "DONOR_REPLY_TIMEOUT_MIN": 30,
    "STOCK_REPLY_TIMEOUT_MIN": 20,
    "WAIT_SLACK_MIN": 120,
    "REST_H": 72,
    "MAX_ASKS_30D": 4,
    "QUIET_HOURS": {"start_h": 22, "end_h": 7, "min_hours_left": 24},
    "SEARCH_RADII_KM": (5, 10, 20, 40),
    "STAFF_GRACE_MIN": 30,
    "STANDBY_PER_UNIT": 2,
    "PROMOTE_TIMEOUT_MIN": 15,
    "DEFAULT_DEFERRAL_DAYS": 30,
    "TEST_MIN": {"PRBC": 720, "SDP": 360},
    "VISIT_MIN": {"PRBC": 45, "SDP": 120},
    "ISSUE_FROM_STOCK_MIN": 45,
    "SAFETY_MARGIN_MIN": 30,
    "CITY_SPEED_KMPH": 18,
    "ROAD_FACTOR": 1.4,
    "REPLY_LAG_MIN": 15,
    "MIN_GO_WINDOW_MIN": 20,
    "STOCK_P": ((6, 0.85), (24, 0.65), (float("inf"), 0.50)),
    "LATENT_RATES": (0.125, 0.25, 0.375),
    "LATENT_PRIOR": (0.25, 0.50, 0.25),
    "REPLY_DELAY_MEAN_MIN": 30,
    "IN_TIME_SHARE": {"window_h": 12, "short": 0.70, "long": 1.0},
    "P_SHOW": 0.90,
    "P_PASS": {"PRBC": 0.88, "SDP": 0.75},
    "STANDBY_FACTOR": 0.80,
    "FAMILY_TRIP_MIN": 45,
    "BASELINE_WAVE": 10,
    "BASELINE_INTERVAL_MIN": 30,
    "LLM_TIMEOUT_S": 8,
    "LLM_MIN_CONFIDENCE": 0.6,
    "ESTIMATOR": "mixture",
    "SIZING": "cost",
    "WAIT_RULE": "slack",
}

REMOVED = ["YES_RATE_PRIOR", "PRIOR_STRENGTH", "NO_REPLY_FACTOR", "STOCK_REPLY_TIMEOUT"]


def agent_section_2_names() -> set[str]:
    text = AGENT_MD.read_text(encoding="utf-8")
    section = text.split("## 2. Numbers", 1)[1].split("## 3.", 1)[0]
    rows = [line for line in section.splitlines() if line.startswith("| `")]
    return {name for row in rows for name in re.findall(r"`([A-Z][A-Z0-9_]+)`", row.split("|")[1])}


def test_every_agent_constant_exists_in_config():
    names = agent_section_2_names()
    assert len(names) >= 35
    missing = [n for n in names if not hasattr(config, n)]
    assert missing == []


def test_expected_covers_agent_section_2():
    assert agent_section_2_names() == set(EXPECTED)


def test_values_match_agent_section_2():
    for name, value in EXPECTED.items():
        assert getattr(config, name) == value, name


def test_removed_constants_absent():
    for name in REMOVED:
        assert not hasattr(config, name), name


def test_tonight_grid_is_ideation_grid_rescaled():
    ideation = (0.3, 0.55, 0.8, 1.05, 1.3)
    mean = sum(f * w for f, w in zip(ideation, config.TONIGHT_WEIGHTS))
    assert abs(mean - 0.7375) < 1e-9
    assert config.TONIGHT_FACTORS == tuple(round(f / mean, 4) for f in ideation)

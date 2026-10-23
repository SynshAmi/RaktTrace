"""Settings from .env and every number from docs/AGENT.md §2 (same names, same values)."""

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

ENV_FILE = Path(__file__).resolve().parents[2] / ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ENV_FILE, extra="ignore")

    telegram_bot_token: str = ""
    telegram_bot_username: str = ""
    llm_enabled: bool = True
    llm_chain: str = ""
    groq_api_key: str = ""
    gemini_api_key: str = ""
    openrouter_api_key: str = ""
    default_scenario: str = "s2_dengue_sdp"
    random_seed: int = 42


settings = Settings()

# --- Targets ---
TARGET_P = 0.90  # Design
ESCALATE_P = 0.30  # Design: below this even the best plan is unlikely
HALFTIME_ESCALATE_P = 0.70  # Design: half the window gone and still below this
DONOR_BURDEN_TAU = 0.015  # Design: one failed request weighs like ~67 donor messages

# --- Waves and rest ---
WAVE_CAP = 10  # Design: max new donors per wave
WAVE_INTERVAL_MIN = 10  # Design
REQUEST_DONOR_CAP = 30  # Design: max donors messaged per request
DONOR_REPLY_TIMEOUT_MIN = 30  # Design
STOCK_REPLY_TIMEOUT_MIN = 20  # Design
WAIT_SLACK_MIN = 120  # Design: go window donors must still have after waiting for stock
REST_H = 72  # Design: not invited in the last 72 h (notification fatigue)
MAX_ASKS_30D = 4  # Design
QUIET_HOURS = {"start_h": 22, "end_h": 7, "min_hours_left": 24}  # Design: only for requests with > 24 h left
SEARCH_RADII_KM = (5, 10, 20, 40)  # Design
STAFF_GRACE_MIN = 30  # Design: reminder at expected time + 30; escalate at + 60
STANDBY_PER_UNIT = 2  # AGENT §5 Step 4: standby donors < 2 × units needed from donors
PROMOTE_TIMEOUT_MIN = 15  # AGENT §5 Step 5: a promoted standby with no answer in 15 min is released
DEFAULT_DEFERRAL_DAYS = 30  # DOMAIN_RULES E10 (Design): deferral length when staff give no date

# --- Timing ---
TEST_MIN = {"PRBC": 720, "SDP": 360}  # Whole-blood testing reported 12–24 h; SDP is an assumption
VISIT_MIN = {"PRBC": 45, "SDP": 120}  # Assumption: registration + screening + collection
ISSUE_FROM_STOCK_MIN = 45  # Reported crossmatch/issue times
SAFETY_MARGIN_MIN = 30  # Design
CITY_SPEED_KMPH = 18  # Assumption: Bengaluru city traffic
ROAD_FACTOR = 1.4  # Assumption: road ≈ 1.4 × straight line
REPLY_LAG_MIN = 15  # AGENT §4: start = now + 15 min for a donor who hasn't replied; also the + 15 in min pipeline
MIN_GO_WINDOW_MIN = 20  # AGENT §4 and §5.1: not invited if the go window is under 20 min

# --- Eligibility (DOMAIN_RULES §2, VERIFIED: D&C Rules donor criteria, G.S.R. 166(E), 2020) ---
MIN_AGE = 18  # E1
WHOLE_BLOOD_MAX_AGE = 65  # E2
FIRST_TIME_MAX_AGE = 60  # E2: first-time whole-blood donors not over 60
APHERESIS_AGE = (18, 60)  # E3
WHOLE_BLOOD_MIN_WEIGHT_KG = 45  # E4
APHERESIS_MIN_WEIGHT_KG = 50  # E5
WHOLE_BLOOD_INTERVAL_DAYS = {"M": 90, "F": 120, None: 120}  # E6: unknown sex → 120
APHERESIS_GAP_H = 48  # E7
APHERESIS_MAX_PER_WEEK = 2  # E7
APHERESIS_MAX_PER_YEAR = 24  # E7
CROSS_PRODUCT_GAP_DAYS = 28  # E8 and E9

# --- Stock chance: (listing age up to, in hours) → chance the listing is true ---
STOCK_P = ((6, 0.85), (24, 0.65), (float("inf"), 0.50))  # Assumption

# --- Donor chance ---
LATENT_RATES = (0.125, 0.25, 0.375)  # Assumption: possible yes rates for tonight; mean 0.25
LATENT_PRIOR = (0.25, 0.50, 0.25)  # Design: prior weight on each rate
REPLY_DELAY_MEAN_MIN = 30  # Assumption: mean time for a donor to reply (same as the sim world)
IN_TIME_SHARE = {"window_h": 12, "short": 0.70, "long": 1.0}  # Assumption: ~30% of yeses are for later
P_SHOW = 0.90  # Assumption
P_PASS = {"PRBC": 0.88, "SDP": 0.75}  # Deferral ~12% whole blood (reported); SDP 25% (assumption)
STANDBY_FACTOR = 0.80  # Design: standby must be re-pinged

# --- Baseline ---
FAMILY_TRIP_MIN = 45  # Assumption: the family travels to the listed centre
BASELINE_WAVE = 10  # Assumption: forwards to ~10 people every 30 min
BASELINE_INTERVAL_MIN = 30  # Assumption

# --- LLM ---
LLM_TIMEOUT_S = 8  # Design
LLM_MIN_CONFIDENCE = 0.6  # Design: below this, treat as unclear
READ_NOW_WINDOW_MIN = 60  # Design: an LLM-read availability time within the next hour means "now" (AGENT §7.2: null for now)

# --- Flags (AGENT §11) ---
ESTIMATOR = "mixture"  # Design: mixture | plugin
SIZING = "cost"  # Design: cost | target | all
WAIT_RULE = "slack"  # Design: slack | lookahead | none

# --- Simulated world (AGENT §9; DOMAIN_RULES §6) ---
SIM_DONOR_COUNT = 300  # AGENT §9: about 300 donors
SIM_DONOR_RADIUS_KM = 15  # AGENT §9: spread within 15 km
SIM_AGE_RANGE = (18, 60)  # AGENT §9
SIM_WEIGHT_RANGE_KG = (45, 90)  # AGENT §9
SIM_PAST_DONATION_SHARE = 0.70  # AGENT §9
SIM_VERIFIED_SHARE = 0.30  # AGENT §9: centre-verified (a subset of past donors)
SIM_APHERESIS_SHARE = 0.15  # AGENT §9
SIM_FEMALE_SHARE = 0.50  # Assumption (sim only)
SIM_LAST_DONATION_DAYS = (20, 400)  # Assumption (sim only): days since a past donation
GROUP_MIX = {  # DOMAIN_RULES §6 seed mix, percent
    "O_POS": 32, "B_POS": 32, "A_POS": 21, "AB_POS": 8,
    "O_NEG": 2.5, "B_NEG": 2.2, "A_NEG": 1.5, "AB_NEG": 0.8,
}
SIM_LISTING_AGE_MIN = (20, 1800)  # AGENT §9: listing age 20 min – 30 h
SIM_LISTING_CHANCE = {"PRBC_POS": 0.6, "PRBC_NEG": 0.25, "SDP": 0.3}  # Assumption (sim only)
SIM_LISTED_UNITS = {"PRBC": (1, 4), "SDP": (1, 1)}  # Assumption (sim only)
SIM_STAFF_REPLY_MIN = (10, 30)  # AGENT §9: staff reply in 10–30 min
TONIGHT_FACTORS = (0.4068, 0.7458, 1.0847, 1.4237, 1.7627)  # AGENT §9: ideation grid ÷ 0.7375, mean 1.0
TONIGHT_WEIGHTS = (0.20, 0.25, 0.25, 0.20, 0.10)  # AGENT §9
SIM_YES_RATE = 0.25  # AGENT §9: yes share = 0.25 × tonight factor
SIM_LATER_SHARE = 0.30  # AGENT §9: share of yeses that are for the next morning
SIM_EXPLICIT_NO_SHARE = 0.35  # AGENT §9: share of non-yes that reply no; the rest stay silent
SIM_REPLY_DELAY_MEAN_MIN = REPLY_DELAY_MEAN_MIN  # AGENT §9: same assumption as the agent

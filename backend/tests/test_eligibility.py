from datetime import datetime, timedelta

from rakt.domain.eligibility import eligibility_failures, is_eligible
from rakt.models import IST, BloodGroup, Channel, Contact, Donor, Product

AT = datetime(2026, 10, 25, 10, 0, tzinfo=IST)
WB, AP = Product.PRBC, Product.SDP


def donor(**overrides) -> Donor:
    fields = dict(
        id="d_x", display_name="Test D.", group=BloodGroup.O_POS, sex="M", age=30, weight_kg=70,
        lat=12.93, lon=77.58, area="Jayanagar", contact=Contact(name="Test D.", channel=Channel.SIM, phone="d_x"),
        apheresis_ok=True,
    )
    return Donor(**{**fields, **overrides})


def days_ago(n: float) -> datetime:
    return AT - timedelta(days=n)


def test_baseline_donor_is_eligible_for_both():
    assert is_eligible(donor(), WB, AT) and is_eligible(donor(), AP, AT)


def test_e1_minimum_age():
    assert "E1" in eligibility_failures(donor(age=17), WB, AT)
    assert "E1" not in eligibility_failures(donor(age=18), WB, AT)


def test_e2_whole_blood_max_age_and_first_timers():
    repeat = days_ago(400)
    assert is_eligible(donor(age=65, last_whole_blood_at=repeat), WB, AT)
    assert "E2" in eligibility_failures(donor(age=66, last_whole_blood_at=repeat), WB, AT)
    assert is_eligible(donor(age=60), WB, AT)
    assert "E2" in eligibility_failures(donor(age=61), WB, AT)  # first-time donor over 60


def test_e3_apheresis_age():
    assert is_eligible(donor(age=60), AP, AT)
    assert "E3" in eligibility_failures(donor(age=61), AP, AT)
    assert "E3" in eligibility_failures(donor(age=17), AP, AT)


def test_e4_e5_weight():
    assert is_eligible(donor(weight_kg=45), WB, AT)
    assert "E4" in eligibility_failures(donor(weight_kg=44), WB, AT)
    assert is_eligible(donor(weight_kg=50), AP, AT)
    assert "E5" in eligibility_failures(donor(weight_kg=49), AP, AT)


def test_e6_men_89_vs_90_days():
    assert "E6" in eligibility_failures(donor(sex="M", last_whole_blood_at=days_ago(89)), WB, AT)
    assert is_eligible(donor(sex="M", last_whole_blood_at=days_ago(90)), WB, AT)


def test_e6_women_119_vs_120_days():
    assert "E6" in eligibility_failures(donor(sex="F", last_whole_blood_at=days_ago(119)), WB, AT)
    assert is_eligible(donor(sex="F", last_whole_blood_at=days_ago(120)), WB, AT)


def test_e6_unknown_sex_uses_120():
    assert "E6" in eligibility_failures(donor(sex=None, last_whole_blood_at=days_ago(119)), WB, AT)
    assert is_eligible(donor(sex=None, last_whole_blood_at=days_ago(120)), WB, AT)


def test_e6_checked_against_donation_time_not_now():
    d = donor(sex="M", last_whole_blood_at=days_ago(89.5))
    assert not is_eligible(d, WB, AT)
    assert is_eligible(d, WB, AT + timedelta(days=1))


def test_e7_apheresis_48_hours_apart():
    assert "E7" in eligibility_failures(donor(apheresis_dates=[AT - timedelta(hours=47)]), AP, AT)
    assert is_eligible(donor(apheresis_dates=[AT - timedelta(hours=48)]), AP, AT)


def test_e7_apheresis_two_per_week():
    one = [AT - timedelta(days=3)]
    two = [AT - timedelta(days=5), AT - timedelta(days=3)]
    assert is_eligible(donor(apheresis_dates=one), AP, AT)  # this one makes 2 in the week
    assert "E7" in eligibility_failures(donor(apheresis_dates=two), AP, AT)  # would be a 3rd
    assert is_eligible(donor(apheresis_dates=[AT - timedelta(days=8), AT - timedelta(days=3)]), AP, AT)


def test_e7_apheresis_24_per_year():
    weekly = [AT - timedelta(days=7 * k) for k in range(1, 24)]  # 23 in the last year
    assert is_eligible(donor(apheresis_dates=weekly), AP, AT)
    assert "E7" in eligibility_failures(donor(apheresis_dates=weekly + [AT - timedelta(days=170.5)]), AP, AT)


def test_e8_whole_blood_then_apheresis_28_days():
    assert "E8" in eligibility_failures(donor(last_whole_blood_at=days_ago(27)), AP, AT)
    assert is_eligible(donor(last_whole_blood_at=days_ago(28)), AP, AT)


def test_e9_apheresis_then_whole_blood_28_days():
    assert "E9" in eligibility_failures(donor(apheresis_dates=[days_ago(27)]), WB, AT)
    assert is_eligible(donor(apheresis_dates=[days_ago(28)]), WB, AT)


def test_e10_active_deferral():
    assert "E10" in eligibility_failures(donor(deferred_until=AT + timedelta(minutes=1)), WB, AT)
    assert is_eligible(donor(deferred_until=AT), WB, AT)


def test_e11_consent():
    assert "E11" in eligibility_failures(donor(consent=False), WB, AT)
    assert "E11" in eligibility_failures(donor(opted_out=True), AP, AT)

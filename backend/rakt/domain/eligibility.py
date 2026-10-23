"""Donor eligibility E1–E11 (DOMAIN_RULES §2), checked at the expected donation time, not "now".

Screening (haemoglobin, BP, recent illness, …) is never checked here: the blood centre decides.
"""

from datetime import datetime, timedelta

from rakt import config
from rakt.models import Donor, Product


def is_first_time(donor: Donor) -> bool:
    return donor.last_whole_blood_at is None and not donor.apheresis_dates


def eligibility_failures(donor: Donor, product: Product, at: datetime) -> list[str]:
    """Ids of the rules the donor fails for this product at time `at`; empty means eligible."""
    whole_blood = product == Product.PRBC
    failures = []

    if donor.age < config.MIN_AGE:
        failures.append("E1")
    if whole_blood:
        if donor.age > config.WHOLE_BLOOD_MAX_AGE or (is_first_time(donor) and donor.age > config.FIRST_TIME_MAX_AGE):
            failures.append("E2")
        if donor.weight_kg < config.WHOLE_BLOOD_MIN_WEIGHT_KG:
            failures.append("E4")
        interval = timedelta(days=config.WHOLE_BLOOD_INTERVAL_DAYS[donor.sex])
        if donor.last_whole_blood_at and at - donor.last_whole_blood_at < interval:
            failures.append("E6")
        if any(at - d < timedelta(days=config.CROSS_PRODUCT_GAP_DAYS) for d in donor.apheresis_dates):
            failures.append("E9")
    else:
        low, high = config.APHERESIS_AGE
        if not low <= donor.age <= high:
            failures.append("E3")
        if donor.weight_kg < config.APHERESIS_MIN_WEIGHT_KG:
            failures.append("E5")
        if apheresis_interval_broken(donor.apheresis_dates, at):
            failures.append("E7")
        if donor.last_whole_blood_at and at - donor.last_whole_blood_at < timedelta(days=config.CROSS_PRODUCT_GAP_DAYS):
            failures.append("E8")

    if donor.deferred_until and at < donor.deferred_until:
        failures.append("E10")
    if not donor.consent or donor.opted_out:
        failures.append("E11")
    return failures


def apheresis_interval_broken(past: list[datetime], at: datetime) -> bool:
    """E7: ≥ 48 h apart, ≤ 2 per week, ≤ 24 per year, counting this donation, over rolling windows."""
    earlier = [d for d in past if d <= at]
    if any(at - d < timedelta(hours=config.APHERESIS_GAP_H) for d in earlier):
        return True
    in_week = sum(at - d < timedelta(days=7) for d in earlier)
    in_year = sum(at - d < timedelta(days=365) for d in earlier)
    return in_week + 1 > config.APHERESIS_MAX_PER_WEEK or in_year + 1 > config.APHERESIS_MAX_PER_YEAR


def is_eligible(donor: Donor, product: Product, at: datetime) -> bool:
    return not eligibility_failures(donor, product, at)

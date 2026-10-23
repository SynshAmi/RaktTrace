"""Timing checks (AGENT §4): can a source's unit be ready for the patient before the deadline?"""

from dataclasses import dataclass
from datetime import datetime, timedelta

from rakt import config
from rakt.domain.geo import Located, travel_min
from rakt.models import Centre, Hospital, Product


def minutes(m: float) -> timedelta:
    return timedelta(minutes=m)


def usable_by(deadline: datetime) -> datetime:
    return deadline - minutes(config.SAFETY_MARGIN_MIN)


@dataclass(frozen=True)
class DonorTiming:
    ready_at: datetime
    on_time: bool
    latest_arrival: datetime
    go_window_min: float

    @property
    def invitable(self) -> bool:
        """Filter 7 (AGENT §5.1): on time, with go window ≥ 20 min."""
        return self.on_time and self.go_window_min >= config.MIN_GO_WINDOW_MIN


def latest_arrival(centre: Centre, hospital: Hospital, product: Product, deadline: datetime) -> datetime:
    pipeline = travel_min(centre, hospital) + config.TEST_MIN[product] + config.VISIT_MIN[product]
    return usable_by(deadline) - minutes(pipeline)


def donor_timing(donor: Located, centre: Centre, hospital: Hospital, product: Product, deadline: datetime,
                 now: datetime, available_from: datetime | None = None, replied: bool = False) -> DonorTiming:
    if available_from is not None:
        start = max(available_from, now)  # an availability time already passed means "now"
    else:
        start = now + minutes(0 if replied else config.REPLY_LAG_MIN)
    pipeline = (travel_min(donor, centre) + config.VISIT_MIN[product] + config.TEST_MIN[product]
                + travel_min(centre, hospital))
    ready_at = start + minutes(pipeline)
    arrival = latest_arrival(centre, hospital, product, deadline)
    return DonorTiming(
        ready_at=ready_at,
        on_time=ready_at <= usable_by(deadline),
        latest_arrival=arrival,
        go_window_min=(arrival - now) / minutes(1),
    )


def stock_ready_at(centre: Centre, hospital: Hospital, now: datetime, reserved: bool) -> datetime:
    wait = 0 if reserved else config.STOCK_REPLY_TIMEOUT_MIN / 2
    return now + minutes(wait + config.ISSUE_FROM_STOCK_MIN + travel_min(centre, hospital))


def stock_on_time(centre: Centre, hospital: Hospital, now: datetime, reserved: bool, deadline: datetime) -> bool:
    return stock_ready_at(centre, hospital, now, reserved) <= usable_by(deadline)


def can_collect(centre: Centre, product: Product) -> bool:
    return centre.accepts_donors and (product != Product.SDP or centre.apheresis)


def donors_can_help(hospital: Hospital, centres: list[Centre], product: Product, now: datetime,
                    deadline: datetime) -> bool:
    pipelines = [
        config.VISIT_MIN[product] + config.TEST_MIN[product] + travel_min(c, hospital)
        for c in centres if can_collect(c, product)
    ]
    if not pipelines:
        return False
    return now + minutes(min(pipelines) + config.REPLY_LAG_MIN) <= usable_by(deadline)


def choose_collection_centre(hospital: Hospital, centres: dict[str, Centre], product: Product,
                             stock_centre_ids: list[str] = ()) -> Centre | None:
    """Own centre if it accepts donors; else a centre already holding stock for this request;
    else the nearest accepting centre. SDP needs apheresis throughout."""
    own = centres.get(hospital.centre_id) if hospital.centre_id else None
    if own and can_collect(own, product):
        return own
    for cid in stock_centre_ids:
        if can_collect(centres[cid], product):
            return centres[cid]
    accepting = [c for c in centres.values() if can_collect(c, product)]
    return min(accepting, key=lambda c: (travel_min(c, hospital), c.id), default=None)

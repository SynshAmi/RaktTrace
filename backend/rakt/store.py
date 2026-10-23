"""In-memory state. One Store per lane or policy; the shared world draws live beside them."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from rakt.models import (
    BaselineState, Centre, Decision, Donor, Hospital, Message, Pledge, Request, Reservation, Stock,
)

if TYPE_CHECKING:
    from rakt.clock import Clock
    from rakt.sim.scenarios import Scenario
    from rakt.sim.world import RequestDraws

LANES = ("rakttrace", "today")


@dataclass
class Store:
    hospitals: dict[str, Hospital] = field(default_factory=dict)
    centres: dict[str, Centre] = field(default_factory=dict)
    stock: list[Stock] = field(default_factory=list)
    donors: dict[str, Donor] = field(default_factory=dict)
    requests: dict[str, Request] = field(default_factory=dict)
    reservations: dict[str, Reservation] = field(default_factory=dict)
    pledges: dict[str, Pledge] = field(default_factory=dict)
    decisions: list[Decision] = field(default_factory=list)
    baselines: dict[str, BaselineState] = field(default_factory=dict)

    def copy(self) -> Store:
        return deepcopy(self)


@dataclass
class AppState:
    clock: Clock
    lanes: dict[str, Store]
    draws: dict[str, RequestDraws] = field(default_factory=dict)  # by request id; shared by every lane
    inbox: dict[str, list[Message]] = field(default_factory=dict)  # sim phone id → messages
    scenario: Scenario | None = None
    message_seq: int = 0

    @property
    def main(self) -> Store:
        return self.lanes["rakttrace"]


def split_lanes(store: Store, names: tuple[str, ...] = LANES) -> dict[str, Store]:
    """Each lane gets its own copy, so one lane's actions never leak into another."""
    return {name: store.copy() for name in names}


state: AppState | None = None


def set_state(new_state: AppState) -> None:
    global state
    state = new_state

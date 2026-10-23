"""Data model (docs/BUILD.md §5). Owned by core; everyone else imports."""

from datetime import datetime, timedelta, timezone
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, Field

IST = timezone(timedelta(hours=5, minutes=30))


class BloodGroup(StrEnum):
    O_POS = "O_POS"
    O_NEG = "O_NEG"
    A_POS = "A_POS"
    A_NEG = "A_NEG"
    B_POS = "B_POS"
    B_NEG = "B_NEG"
    AB_POS = "AB_POS"
    AB_NEG = "AB_NEG"


class Product(StrEnum):
    PRBC = "PRBC"
    SDP = "SDP"


class RequestStatus(StrEnum):
    OPEN = "OPEN"
    COVERED = "COVERED"
    SECURED = "SECURED"
    FULFILLED = "FULFILLED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class BaselineStatus(StrEnum):
    SEARCHING = "SEARCHING"
    SAYS_FULFILLED = "SAYS_FULFILLED"


class ReservationStatus(StrEnum):
    PENDING = "PENDING"
    RESERVED = "RESERVED"
    READY = "READY"
    NONE = "NONE"
    EXPIRED = "EXPIRED"
    RELEASED = "RELEASED"


class PledgeStatus(StrEnum):
    INVITED = "INVITED"
    NO_REPLY = "NO_REPLY"
    DECLINED = "DECLINED"
    TOO_LATE = "TOO_LATE"
    ACTIVE = "ACTIVE"
    STANDBY = "STANDBY"
    ARRIVED = "ARRIVED"
    COLLECTED = "COLLECTED"
    READY = "READY"
    DEFERRED = "DEFERRED"
    NO_SHOW = "NO_SHOW"
    FAILED_TEST = "FAILED_TEST"
    RELEASED = "RELEASED"
    OPTED_OUT = "OPTED_OUT"


class Intent(StrEnum):
    YES = "YES"
    NO = "NO"
    STOP = "STOP"
    UNCLEAR = "UNCLEAR"


class Channel(StrEnum):
    SIM = "sim"
    TELEGRAM = "telegram"


GROUP_LABELS = {
    BloodGroup.O_POS: "O+", BloodGroup.O_NEG: "O−", BloodGroup.A_POS: "A+", BloodGroup.A_NEG: "A−",
    BloodGroup.B_POS: "B+", BloodGroup.B_NEG: "B−", BloodGroup.AB_POS: "AB+", BloodGroup.AB_NEG: "AB−",
}
PRODUCT_LABELS = {Product.PRBC: "Red cells", Product.SDP: "Platelets (SDP)"}

ReadBy = Literal["llm", "rules"]


# --- Shared types ---

class Button(BaseModel):
    id: str
    title: str


class Contact(BaseModel):
    name: str
    channel: Channel
    chat_id: str | None = None
    phone: str | None = None  # for sim contacts: the sim phone id


class Outgoing(BaseModel):
    to: Contact
    kind: str
    body: str
    buttons: list[Button] = Field(default_factory=list)
    request_id: str | None = None


class Inbound(BaseModel):
    channel: Channel
    sender_id: str
    text: str | None = None
    button_id: str | None = None
    at: datetime


class PleaDraft(BaseModel):
    group: BloodGroup | None = None
    product: Product | None = None
    units: int | None = None
    hospital_id: str | None = None
    deadline_at: datetime | None = None
    missing: list[str] = Field(default_factory=list)
    confidence: float = 0.0
    read_by: ReadBy = "rules"


class ReplyRead(BaseModel):
    intent: Intent
    available_from: datetime | None = None
    confidence: float = 0.0
    read_by: ReadBy = "rules"


class DonorProfile(BaseModel):
    """Synthetic donor answers from Telegram onboarding (PRODUCT §2.2). Approximate area only, never an address."""
    group: BloodGroup
    area: str
    sex: Literal["M", "F"] | None = None
    age: int
    weight_kg: int
    apheresis_ok: bool = False
    last_donation: Literal["never", "over_4_months", "recent"] = "never"
    lat: float | None = None  # set by demo templates; otherwise the area's centre is used
    lon: float | None = None


# --- State ---

class Hospital(BaseModel):
    id: str
    name: str
    area: str
    lat: float
    lon: float
    centre_id: str | None = None


class Centre(BaseModel):
    id: str
    name: str
    area: str
    address: str
    lat: float
    lon: float
    phone: str
    accepts_donors: bool
    apheresis: bool
    contact: Contact


class Stock(BaseModel):
    centre_id: str
    product: Product
    group: BloodGroup
    listed_units: int
    listed_at: datetime
    true_units: int  # hidden from the API and the agent


class Donor(BaseModel):
    id: str
    display_name: str
    group: BloodGroup
    sex: Literal["M", "F"] | None
    age: int
    weight_kg: int
    lat: float
    lon: float
    area: str
    contact: Contact
    consent: bool = True
    opted_out: bool = False
    apheresis_ok: bool = False
    last_whole_blood_at: datetime | None = None
    apheresis_dates: list[datetime] = Field(default_factory=list)
    donation_verified: bool = False
    deferred_until: datetime | None = None
    invites: list[datetime] = Field(default_factory=list)
    telegram_demo: bool = False


class Request(BaseModel):
    id: str
    group: BloodGroup
    product: Product
    units: int
    hospital_id: str
    deadline_at: datetime
    created_at: datetime
    status: RequestStatus = RequestStatus.OPEN
    escalation_level: int = 0
    radius_km: float
    collection_centre_id: str | None = None
    family: Contact | None = None
    brief: str | None = None


class Reservation(BaseModel):
    id: str
    request_id: str
    centre_id: str
    group: BloodGroup
    units_asked: int
    units_reserved: int = 0
    status: ReservationStatus = ReservationStatus.PENDING
    listed_at: datetime
    asked_at: datetime
    ready_at: datetime | None = None


class Pledge(BaseModel):
    id: str
    request_id: str
    donor_id: str
    status: PledgeStatus = PledgeStatus.INVITED
    wave: int
    invited_at: datetime
    replied_at: datetime | None = None
    reply_text: str | None = None
    available_from: datetime | None = None
    booking_code: str | None = None
    on_way_at: datetime | None = None  # an ACTIVE donor tapped "On my way" (no status change: still ACTIVE)
    ready_at: datetime | None = None
    why: str = ""


class Decision(BaseModel):
    id: str
    request_id: str
    at: datetime
    trigger: str
    p_before: float
    p_after: float
    status: RequestStatus
    actions: list[str] = Field(default_factory=list)
    summary: str


class Message(BaseModel):
    id: str
    at: datetime
    direction: Literal["out", "in"]
    channel: Channel
    to_name: str
    request_id: str | None = None
    kind: str
    body: str
    buttons: list[Button] = Field(default_factory=list)
    read_by: Literal["llm", "rules", "button"] | None = None


class BaselineState(BaseModel):
    request_id: str
    status: BaselineStatus = BaselineStatus.SEARCHING
    said_fulfilled_at: datetime | None = None
    found_units: int = 0
    donors_messaged: int = 0
    timeline: list[str] = Field(default_factory=list)

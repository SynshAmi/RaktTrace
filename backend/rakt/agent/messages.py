"""Message copy (PRODUCT §5). Channels only deliver what is rendered here."""

from datetime import datetime

from rakt.models import GROUP_LABELS, PRODUCT_LABELS, Button, Centre, Hospital, Outgoing, Request, Reservation


def when(at: datetime) -> str:
    return at.strftime("%H:%M, %d %b")


def staff_hold(request: Request, res: Reservation, centre: Centre, hospital: Hospital) -> Outgoing:
    body = (f"RaktTrace · {request.id}: can you reserve {res.units_asked} unit(s) of {GROUP_LABELS[res.group]} "
            f"{PRODUCT_LABELS[request.product]} for a patient at {hospital.name}, needed by {when(request.deadline_at)}?")
    buttons = [
        Button(id=f"R:{res.id}:ALL", title=f"Reserve {res.units_asked}"),
        Button(id=f"R:{res.id}:SOME", title="Some"),
        Button(id=f"R:{res.id}:NONE", title="None"),
    ]
    return Outgoing(to=centre.contact, kind="staff_hold", body=body, buttons=buttons, request_id=request.id)


def staff_hold_count(request: Request, res: Reservation, centre: Centre) -> Outgoing:
    """After "Some": pick how many (button ids N{k}, BUILD §5.3)."""
    counts = range(1, max(res.units_asked, 2))
    buttons = [Button(id=f"R:{res.id}:N{k}", title=str(k)) for k in counts]
    return Outgoing(to=centre.contact, kind="staff_hold_count", body=f"{request.id}: how many units can you reserve?",
                    buttons=buttons, request_id=request.id)


def staff_release(request: Request, centre: Centre) -> Outgoing:
    return Outgoing(to=centre.contact, kind="staff_release",
                    body=f"{request.id}: the reservation is no longer needed. Thank you!", request_id=request.id)

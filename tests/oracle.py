"""An independent reading of the task instructions, written without the plugin's rules module (its own
date arithmetic with datetime, its own order of tests), to cross-check the answer key offer by offer. A
flight's day is the local date where it leaves, worked out here from its UTC time and the airport's offset,
not read from depart_local."""

from __future__ import annotations

from datetime import date, datetime, timedelta

from plugin.world import AIRPORTS

OFFSETS = {row[0]: row[5] for row in AIRPORTS}


def day(text: str) -> date:
    return date.fromisoformat(text[:10])


def local_day(segment) -> date:
    """The local date at a segment's origin of its UTC departure."""
    return (datetime.fromisoformat(segment.depart) + timedelta(minutes=OFFSETS[segment.origin])).date()


def visit_answer(request, booking_date: str, miles: int, offers) -> tuple[str, set[str]]:
    """(refusal, the correct offer ids) for a visit request booked on ``booking_date``."""
    start, end = day(request.assignment_start), day(request.assignment_end)
    out, back = day(request.outbound_date), day(request.return_date)
    status = request.family_status.value
    if not 91 <= (end - start).days + 1 <= 365:
        return "NOT_A_TDA", set()
    if not request.duplicate_housing_obligation:
        return "NO_DUPLICATE_HOUSING", set()
    if status == "ACCOMPANIED":
        return "ACCOMPANIED", set()
    if not request.manager_approved:
        return "NO_MANAGER_APPROVAL", set()
    if miles < 400:
        return "UNDER_400_MILES", set()
    if not (start <= out and back <= end):
        return "OUTSIDE_ASSIGNMENT", set()
    previous = day(request.last_home_visit) if request.last_home_visit else start
    if (out - previous).days < (28 if status == "SINGLE" else 14):
        return "TOO_SOON", set()
    if (out - day(booking_date)).days < 14:
        return "UNDER_14_DAYS_ADVANCE", set()
    fine = [
        o for o in offers
        if o.ticket.value == "ROUND_TRIP" and o.cabin.value == "ECONOMY" and o.refundable is False
        and local_day(o.outbound[0]) == out and local_day(o.inbound[0]) == back
        and o.outbound[0].origin == request.tda_airport.value and o.inbound[-1].destination == request.tda_airport.value
        and o.outbound[-1].destination == request.home_airport.value
    ]
    if not fine:
        return "NO_COMPLIANT_FLIGHT", set()
    cheapest = min(o.fare_cents for o in fine)
    return "NONE", {o.offer_id for o in fine if o.fare_cents == cheapest}

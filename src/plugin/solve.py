"""solve_booking, the reference tool: the visit booked as of today, every offer on its days and the refusal
or booking the rules require, pinned before the agent starts and never shown to it."""

from pathlib import Path

from contract import SolveOutput, TripInput
from plugin import receipts, world
from plugin.rules import solve


def solve_booking(value: TripInput, workspace: Path) -> SolveOutput:
    stamp = receipts.CLOCK()
    trip = world.make_trip(value, stamp[:10])
    offers = world.offers_for(trip.tda.code, trip.home.code, trip.outbound_date, trip.return_date)
    answer = solve(trip, offers)
    return SolveOutput(
        pinned_at=stamp,
        trip=trip,
        offers=offers,
        refusal=answer.refusal,
        compliant_offer_ids=answer.compliant,
        lowest_fare_cents=answer.lowest_fare_cents,
        correct_offer_ids=answer.correct,
    )

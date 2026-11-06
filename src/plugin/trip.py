"""get_trip: the home visit a request describes, booked as of today, and a new run to book it in."""

from pathlib import Path

from contract import TripInput, TripOutput
from plugin import receipts, world
from plugin.rules import request_plain


def get_trip(value: TripInput, workspace: Path) -> TripOutput:
    stamp = receipts.CLOCK()
    trip = world.make_trip(value, stamp[:10])
    run_id = receipts.new_run(workspace, request_plain(value), trip.booking_date, stamp)
    return TripOutput(run_id=run_id, trip=trip)

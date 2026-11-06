"""search_flights: the round-trip offers out on one day and back on another."""

from pathlib import Path

from contract import SearchInput, SearchOutput
from plugin import receipts, world
from plugin.rules import LONGEST_VISIT_DAYS, booking_date_problem, days_between, offers_digest


def search_flights(value: SearchInput, workspace: Path) -> SearchOutput:
    if value.origin is value.destination:
        raise ValueError("origin and destination are the same airport")
    stay = days_between(value.outbound_date, value.return_date)
    if not 0 <= stay <= LONGEST_VISIT_DAYS:
        raise ValueError(f"return_date must be 0 to {LONGEST_VISIT_DAYS} days after outbound_date")
    # In a booking run, today is the run's booking date; a search outside a run (run_id empty) is only shown.
    folder, started = receipts.run_trip(workspace, value.run_id) if value.run_id else (None, None)
    today = started["booking_date"] if started else receipts.CLOCK()[:10]
    problem = booking_date_problem(value.outbound_date, value.return_date, today)
    if problem:
        raise ValueError(problem)
    offers = world.offers_for(value.origin.value, value.destination.value, value.outbound_date, value.return_date)
    if folder is not None:
        receipts.add_search(
            folder,
            {
                "origin": value.origin.value,
                "destination": value.destination.value,
                "outbound_date": value.outbound_date,
                "return_date": value.return_date,
                "offer_ids": [offer.offer_id for offer in offers],
                "digest": offers_digest(offers),
            },
        )
    return SearchOutput(run_id=value.run_id, note=world.NOTE, offers=offers)

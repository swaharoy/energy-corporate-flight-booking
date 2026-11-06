"""search_flights' checks: a well-formed query, and exactly the simulated world's offers for it."""

from .checks import RUN_ID, result
from .rules import LONGEST_VISIT_DAYS, days_between, is_date, same_offers
from .world import NOTE, offers_for


def verify_input(value):
    if value.origin is value.destination:
        return result(False, f"origin and destination are both {value.origin.value}")
    for name, date in (("outbound_date", value.outbound_date), ("return_date", value.return_date)):
        if not is_date(date):
            return result(False, f"{name} {date!r} is not a real YYYY-MM-DD date")
    if not 0 <= days_between(value.outbound_date, value.return_date) <= LONGEST_VISIT_DAYS:
        return result(False, f"return_date must be 0 to {LONGEST_VISIT_DAYS} days after outbound_date")
    if value.run_id and not RUN_ID.fullmatch(value.run_id):
        return result(False, f"run_id {value.run_id!r} is not one get_trip returned")
    return result(True, "a well-formed search")


def verify_output(input_value, output_value, workspace):
    q = input_value
    if output_value.run_id != q.run_id:
        return result(False, "the result names another run")
    if output_value.note != NOTE:
        return result(False, "the result does not say its fares and schedules are simulated")
    expected = offers_for(q.origin.value, q.destination.value, q.outbound_date, q.return_date)
    if not same_offers(output_value.offers, expected):
        return result(False, "the offers are not the route's offers on the searched days")
    return result(True, f"{len(expected)} offers {q.origin.value}-{q.destination.value}, out {q.outbound_date}, "
                        f"back {q.return_date}")

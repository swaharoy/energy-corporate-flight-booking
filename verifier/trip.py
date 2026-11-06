"""get_trip's checks: a request that can be booked, the trip it makes, and the run it began."""

from .checks import RUN_ID, read_json, result
from .rules import is_date, request_plain, request_problem
from .world import make_trip


def verify_input(value):
    problem = request_problem(value)
    return result(problem is None, problem or "a well-formed home-visit request")


def verify_output(input_value, output_value, workspace):
    trip = output_value.trip
    if not is_date(trip.booking_date):
        return result(False, f"booking_date {trip.booking_date!r} is not a real YYYY-MM-DD date")
    try:
        expected = make_trip(input_value, trip.booking_date)
    except ValueError as error:
        return result(False, f"the request cannot be booked on {trip.booking_date}: {error}")
    if trip != expected:
        return result(False, "the trip is not the one the request makes on its booking date")
    if not RUN_ID.fullmatch(output_value.run_id):
        return result(False, f"run_id {output_value.run_id!r} is not a run id")
    receipt = read_json(f"{workspace}/runs/{output_value.run_id}/trip.json")
    if (
        receipt is None
        or receipt.get("request") != request_plain(input_value)
        or receipt.get("booking_date") != trip.booking_date
    ):
        return result(False, f"run {output_value.run_id} has no receipt for this request in the workspace")
    return result(True, f"the visit of the request, booked {trip.booking_date}, run {output_value.run_id}")

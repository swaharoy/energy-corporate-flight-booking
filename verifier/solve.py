"""solve_booking's checks: the pinned trip is the request's, its offers are the simulated world's, and its
answer is what the rules give for them."""

from .checks import result
from .rules import is_date, request_problem, same_offers, solve
from .world import make_trip, offers_for


def verify_input(value):
    problem = request_problem(value)
    return result(problem is None, problem or "a well-formed home-visit request")


def verify_output(input_value, output_value, workspace):
    problem = answer_key_problem(input_value, output_value)
    return result(problem is None, problem or "the answer key follows the rules")


def answer_key_problem(request, key):
    """What is wrong with a pinned answer key for ``request``, or None."""
    trip = key.trip
    if not is_date(trip.booking_date) or not key.pinned_at.startswith(trip.booking_date + " "):
        return "the answer key's booking date is not the day it was pinned"
    try:
        expected = make_trip(request, trip.booking_date)
    except ValueError as error:
        return f"the answer key's trip cannot be booked: {error}"
    if trip != expected:
        return "the answer key's trip is not the one the request makes"
    if not same_offers(key.offers, offers_for(trip.tda.code, trip.home.code, trip.outbound_date, trip.return_date)):
        return "the answer key's offers are not the route's offers on the visit's days"
    answer = solve(trip, key.offers)
    pinned = (key.refusal, key.compliant_offer_ids, key.lowest_fare_cents, key.correct_offer_ids)
    computed = (answer.refusal, answer.compliant, answer.lowest_fare_cents, answer.correct)
    if pinned != computed:
        return "the answer key's booking is not what the rules give for its trip and offers"
    return None

"""The shared rules on their own: dates, what a request may be, rules C1-C10 in order and at every
boundary, on trips made from requests and on hand-built offers."""

from __future__ import annotations

from datetime import date, timedelta

import pytest
from helpers import TODAY, hand_built, offer, plain_request, request
from slimconfig import build_output

from contract import Offer, Refusal
from plugin import world
from plugin.rules import (
    assignment_days,
    booking_date_problem,
    date_of,
    day_number,
    fare_compliant,
    flies_trip,
    is_date,
    minute_number,
    request_problem,
    solve,
    trip_refusal,
)


def trip(miles: int = 1035, **changes):
    with hand_built(miles=miles):
        return world.make_trip(request(**changes), TODAY)


def offers(*plain):
    return [build_output(value, Offer) for value in plain]


# Dates ---------------------------------------------------------------------------------------------


def test_day_numbers_agree_with_the_calendar() -> None:
    first = date(1999, 12, 25)
    for step in range(0, 20_000, 7):
        day = first + timedelta(days=step)
        assert day_number(day.isoformat()) == (day - date(1970, 1, 1)).days
        assert date_of(day_number(day.isoformat())) == day.isoformat()


@pytest.mark.parametrize("text", ["2026-02-29", "2026-13-01", "2026-1-01", "", "2026-12-04 10:00", "x"])
def test_not_dates(text: str) -> None:
    assert not is_date(text)


def test_minutes_and_assignment_days() -> None:
    assert minute_number("1970-01-02 01:30") == 1440 + 90
    assert assignment_days("2026-01-01", "2026-01-01") == 1
    assert assignment_days("2026-01-01", "2026-03-31") == 90
    assert assignment_days("2026-01-01", "2026-04-01") == 91


# Requests ------------------------------------------------------------------------------------------


def test_a_good_request_has_no_problem() -> None:
    assert request_problem(request()) is None
    assert request_problem(request(last_home_visit="")) is None


@pytest.mark.parametrize(
    ("changes", "words"),
    [
        ({"traveller_name": "  "}, "blank"),
        ({"traveller_name": "x" * 81}, "longer"),
        ({"home_airport": "IAH"}, "two different airports"),
        ({"assignment_start": "2026-02-30"}, "not a real"),
        ({"outbound_date": "12/04/2026"}, "not a real"),
        ({"last_home_visit": "soon"}, "not a real"),
        ({"assignment_end": "2026-08-31"}, "before assignment_start"),
        ({"return_date": "2026-12-03"}, "before outbound_date"),
        ({"return_date": "2027-01-04"}, "at most 30 days"),
        ({"last_home_visit": "2026-08-31"}, "before the assignment starts"),
        ({"last_home_visit": "2026-12-04"}, "not before outbound_date"),
    ],
)
def test_bad_requests_are_named(changes: dict, words: str) -> None:
    assert words in request_problem(request(**changes))


def test_flights_must_leave_today_or_later_and_within_the_horizon() -> None:
    assert booking_date_problem(TODAY, TODAY, TODAY) is None
    assert "past" in booking_date_problem("2026-11-04", "2026-11-06", TODAY)
    assert booking_date_problem("2027-09-30", "2027-10-01", TODAY) is None
    assert "far ahead" in booking_date_problem("2027-09-30", "2027-10-02", TODAY)


def test_the_trip_states_the_derived_facts() -> None:
    made = trip()
    assert made.assignment_days == 181 and made.days_since_previous_visit == 32 and made.days_before_departure == 29
    assert trip(last_home_visit="").days_since_previous_visit == day_number("2026-12-04") - day_number("2026-09-01")
    assert world.make_trip(request(), TODAY).estimated_driving_miles == world.driving_miles("IAH", "DEN") == 1035


# C1-C8, in order and at their boundaries --------------------------------------------------------------


def span(days: int) -> dict:
    """An assignment of ``days`` days from 2026-10-01 (the visit is inside it, 64 days after the start)."""
    return {"assignment_start": "2026-10-01", "assignment_end": date_of(day_number("2026-10-01") + days - 1),
            "last_home_visit": ""}


@pytest.mark.parametrize(
    ("days", "refusal"),
    [(90, Refusal.NOT_A_TDA), (91, Refusal.NONE), (365, Refusal.NONE), (366, Refusal.NOT_A_TDA)],
)
def test_c1_a_tda_lasts_91_to_365_days(days: int, refusal: Refusal) -> None:
    assert trip_refusal(trip(**span(days))) is refusal


@pytest.mark.parametrize(
    ("changes", "refusal"),
    [
        ({"duplicate_housing_obligation": False}, Refusal.NO_DUPLICATE_HOUSING),
        ({"family_status": "ACCOMPANIED"}, Refusal.ACCOMPANIED),
        ({"manager_approved": False}, Refusal.NO_MANAGER_APPROVAL),
    ],
)
def test_c2_to_c4_refuse_the_visit(changes: dict, refusal: Refusal) -> None:
    assert trip_refusal(trip(**changes)) is refusal


@pytest.mark.parametrize(("miles", "refusal"), [(399, Refusal.UNDER_400_MILES), (400, Refusal.NONE)])
def test_c5_airfare_from_exactly_400_miles(miles: int, refusal: Refusal) -> None:
    assert trip_refusal(trip(miles=miles)) is refusal


@pytest.mark.parametrize(
    ("changes", "refusal"),
    [
        ({"return_date": "2027-02-28", "outbound_date": "2027-02-25", "last_home_visit": ""}, Refusal.NONE),
        ({"return_date": "2027-03-01", "outbound_date": "2027-02-25", "last_home_visit": ""},
         Refusal.OUTSIDE_ASSIGNMENT),
        ({"assignment_start": "2026-12-05", "assignment_end": "2027-04-30", "last_home_visit": ""},
         Refusal.OUTSIDE_ASSIGNMENT),
    ],
)
def test_c6_the_visit_is_within_the_assignment(changes: dict, refusal: Refusal) -> None:
    assert trip_refusal(trip(**changes)) is refusal


@pytest.mark.parametrize(
    ("status", "last", "refusal"),
    [
        ("SINGLE", "2026-11-06", Refusal.NONE),  # 28 days before 2026-12-04
        ("SINGLE", "2026-11-07", Refusal.TOO_SOON),  # 27 days
        ("UNACCOMPANIED", "2026-11-20", Refusal.NONE),  # 14 days
        ("UNACCOMPANIED", "2026-11-21", Refusal.TOO_SOON),  # 13 days
    ],
)
def test_c7_one_visit_every_four_or_two_weeks(status: str, last: str, refusal: Refusal) -> None:
    assert trip_refusal(trip(family_status=status, last_home_visit=last)) is refusal


def test_c7_counts_from_the_assignment_start_without_a_visit() -> None:
    start = {"assignment_start": "2026-11-06", "assignment_end": "2027-03-31", "last_home_visit": ""}
    assert trip_refusal(trip(**start)) is Refusal.NONE  # 28 days after the start
    assert trip_refusal(trip(**start | {"assignment_start": "2026-11-07"})) is Refusal.TOO_SOON


@pytest.mark.parametrize(("outbound", "refusal"), [("2026-11-19", Refusal.NONE), ("2026-11-18", Refusal.UNDER_14_DAYS_ADVANCE)])
def test_c8_a_14_day_advance_purchase(outbound: str, refusal: Refusal) -> None:
    changes = {"outbound_date": outbound, "return_date": "2026-11-22", "last_home_visit": ""}
    assert trip_refusal(trip(**changes)) is refusal


def test_the_first_rule_broken_gives_the_refusal() -> None:
    every = {"assignment_end": "2026-10-31", "duplicate_housing_obligation": False, "family_status": "ACCOMPANIED",
             "manager_approved": False, "last_home_visit": ""}
    assert trip_refusal(trip(miles=100, **every)) is Refusal.NOT_A_TDA
    every.pop("assignment_end")
    assert trip_refusal(trip(miles=100, **every)) is Refusal.NO_DUPLICATE_HOUSING
    every.pop("duplicate_housing_obligation")
    assert trip_refusal(trip(miles=100, **every)) is Refusal.ACCOMPANIED
    every.pop("family_status")
    assert trip_refusal(trip(miles=100, **every)) is Refusal.NO_MANAGER_APPROVAL
    every.pop("manager_approved")
    assert trip_refusal(trip(miles=100, **every)) is Refusal.UNDER_400_MILES
    soon = {"outbound_date": "2026-11-10", "return_date": "2026-11-12", "last_home_visit": "2026-11-01"}
    assert trip_refusal(trip(**soon)) is Refusal.TOO_SOON
    assert trip_refusal(trip(**soon | {"last_home_visit": "2026-10-01"})) is Refusal.UNDER_14_DAYS_ADVANCE


# C9 and C10 ----------------------------------------------------------------------------------------------


def test_c9_only_round_trip_economy_non_refundable() -> None:
    assert fare_compliant(build_output(offer("a", 1), Offer))
    for changes in ({"ticket": "TWO_ONE_WAYS"}, {"cabin": "BUSINESS"}, {"cabin": "FIRST"}, {"refundable": True}):
        assert not fare_compliant(build_output(offer("a", 1, **changes), Offer))


def test_c10_the_cheapest_compliant_fare_with_ties() -> None:
    found = offers(offer("1", 30_000, ticket="TWO_ONE_WAYS"), offer("2", 25_000, refundable=True),
                   offer("3", 26_000, cabin="FIRST"), offer("4", 40_000), offer("5", 40_000), offer("6", 40_001))
    answer = solve(trip(), found)
    assert answer.refusal is Refusal.NONE and answer.compliant == ["4", "5", "6"]
    assert answer.lowest_fare_cents == 40_000 and answer.correct == ["4", "5"]


def test_c9_nothing_compliant_is_refused() -> None:
    found = offers(offer("1", 30_000, ticket="TWO_ONE_WAYS"), offer("2", 25_000, refundable=True))
    assert solve(trip(), found).refusal is Refusal.NO_COMPLIANT_FLIGHT
    assert solve(trip(), []).refusal is Refusal.NO_COMPLIANT_FLIGHT


def test_an_offer_on_other_days_or_route_does_not_fly_the_visit() -> None:
    made = trip()
    assert flies_trip(made, build_output(offer("1", 1), Offer))
    assert not flies_trip(made, build_output(offer("1", 1, back="2026-12-08 15:00"), Offer))
    assert not flies_trip(made, build_output(offer("1", 1, out="2026-12-03 15:00"), Offer))
    assert not flies_trip(made, build_output(offer("1", 1, route=("IAH", "DFW")), Offer))
    assert solve(made, offers(offer("1", 1, route=("IAH", "DFW")))).refusal is Refusal.NO_COMPLIANT_FLIGHT


def test_an_evening_departure_west_of_utc_flies_on_its_local_date() -> None:
    """19:00 at LAX on Dec 4 is 03:00 UTC on Dec 5: it still leaves on Dec 4, the requested day."""
    made = trip(tda_airport="LAX", home_airport="DEN")
    late = build_output(offer("1", 1, route=("LAX", "DEN"), out="2026-12-04 19:00"), Offer)
    assert late.outbound[0].depart == "2026-12-05 03:00" and late.outbound[0].depart_local == "2026-12-04 19:00"
    assert flies_trip(made, late)
    assert solve(made, [late]).correct == ["1"]
    early = build_output(offer("2", 1, route=("LAX", "DEN"), out="2026-12-03 19:00"), Offer)
    assert early.outbound[0].depart.startswith("2026-12-04") and not flies_trip(made, early)


def test_a_refused_visit_books_nothing_whatever_the_offers() -> None:
    answer = solve(trip(manager_approved=False), offers(offer("1", 1)))
    assert (answer.refusal, answer.compliant, answer.lowest_fare_cents, answer.correct) == (
        Refusal.NO_MANAGER_APPROVAL, [], 0, [])


def test_plain_request_defaults_pass_c1_to_c8() -> None:
    assert trip_refusal(trip(**plain_request())) is Refusal.NONE

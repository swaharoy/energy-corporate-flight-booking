"""The simulated world: real U.S. airports and airlines on plausible routes, synthetic but realistic round-trip
fares and schedules, the same on every machine; the driving-distance estimate; and an answer key that agrees
with an independent reading of the rules."""

from __future__ import annotations

import hashlib
import itertools
import json
import re
from pathlib import Path

import pytest
from helpers import CODES, TODAY, requests
from oracle import visit_answer
from slimconfig import plain_output

from contract import AirportCode, Cabin, SearchInput, TicketType
from plugin import receipts, search_flights, solve_booking, world
from plugin.rules import date_of, day_number, minute_number

DAY = day_number("2026-12-04")
GOLDEN = {
    ("IAH", "DEN"): "b209b26cce2bea36",
    ("SFO", "JFK"): "4386660f810fdae7",
    ("IAH", "BNA"): "2deb0bd6d6bab036",
    ("ATL", "SEA"): "fcccca22168db1c0",
    ("HNL", "LAX"): "8642c79b78b1164d",
}
FLIGHT_NUMBER = re.compile(r"^(DL|UA|AA|AS|B6|WN) [1-9]\d{0,3}$")
OFFER_ID = re.compile(r"^\d{8}-\d{8}-\d{2}$")
LARGEST_SEARCH_CHARS = 12_000  # one search must stay far inside the hosted model's 65,536-token budget


def routes(step: int = 3):
    """Every ``step``-th route of all 31 x 30."""
    pairs = [(a, b) for a in CODES for b in CODES if a != b]
    return pairs[::step]


def digest(offers) -> str:
    text = json.dumps([plain_output(offer) for offer in offers], sort_keys=True)
    return hashlib.sha256(text.encode()).hexdigest()[:16]


@pytest.mark.parametrize("route", sorted(GOLDEN))
def test_a_route_and_its_days_make_the_same_offers_everywhere(route) -> None:
    assert digest(world.trip_offers(*route, DAY, DAY + 3)) == GOLDEN[route]


def test_the_airports_are_the_contract_codes_all_in_the_us() -> None:
    assert [row[0] for row in world.AIRPORTS] == [member.value for member in AirportCode]
    assert len(world.AIRPORTS) == 31
    assert all(-600 <= row[5] <= -300 and row[5] % 60 == 0 for row in world.AIRPORTS)


def test_the_airlines_are_real_us_airlines_with_hubs_among_the_airports() -> None:
    names = {row[1] for row in world.AIRLINES}
    assert names == {"Delta Air Lines", "United Airlines", "American Airlines", "Alaska Airlines", "JetBlue",
                     "Southwest Airlines"}
    for row in world.AIRLINES:
        assert set(row[4]) <= set(CODES)


def test_driving_miles_are_the_great_circle_times_1_2() -> None:
    assert world.driving_miles("IAH", "DEN") == world.driving_miles("DEN", "IAH") == 1035
    assert world.driving_miles("JFK", "BOS") < 400 < world.driving_miles("LAX", "SFO")
    for a, b in routes(7):
        miles = world.great_circle_km(a, b) / 1.609344
        assert world.driving_miles(a, b) == round(miles * 1.2)


def test_offers_are_plausible_on_every_route() -> None:
    for a, b in routes(1):
        check_plausible(a, b, world.trip_offers(a, b, DAY, DAY + 3))


def check_plausible(a: str, b: str, offers) -> None:
    assert len(json.dumps([plain_output(o) for o in offers])) < LARGEST_SEARCH_CHARS
    for offer in offers:
        assert OFFER_ID.fullmatch(offer.offer_id) and offer.offer_id.startswith("20261204-20261207-")
        out, back = offer.outbound, offer.inbound
        assert out[0].origin == a and out[-1].destination == b and back[0].origin == b and back[-1].destination == a
        assert out[0].depart_local.startswith("2026-12-04") and back[0].depart_local.startswith("2026-12-07")
        for legs in (out, back):
            first_local = int(legs[0].depart_local[11:13]) * 60 + int(legs[0].depart_local[14:16])
            assert world.FIRST_DEPARTURE <= first_local <= world.LAST_DEPARTURE - 5
            for first, second in itertools.pairwise(legs):
                gap = minute_number(second.depart) - minute_number(first.arrive)
                assert 45 <= gap <= 240
            for segment in legs:
                assert FLIGHT_NUMBER.fullmatch(segment.flight_number)
                assert minute_number(segment.arrive) - minute_number(segment.depart) == segment.air_minutes
                local = minute_number(segment.depart) + world.utc_offset(segment.origin)
                assert segment.depart_local == world.time_text(local)
        assert 10_000 <= offer.fare_cents <= 900_000
        if offer.ticket is TicketType.TWO_ONE_WAYS:
            assert offer.cabin is Cabin.ECONOMY and not offer.refundable


WEST_COAST = ("LAX", "SFO", "SEA", "SAN", "LAS")


def local_minute(segment) -> int:
    return int(segment.depart_local[11:13]) * 60 + int(segment.depart_local[14:16])


def test_west_coast_airports_have_evening_departures() -> None:
    """A day is the local date where a flight leaves, so a UTC-8 airport has flights after 16:00 local too."""
    for code in WEST_COAST:
        late = [
            segment for other in CODES if other != code
            for flight in world.day_flights(code, other, DAY) for segment in flight[1][:1]
            if local_minute(segment) >= 16 * 60
        ]
        assert late, code
        assert all(segment.depart_local.startswith("2026-12-04") for segment in late)
        assert any(segment.depart[:10] == "2026-12-05" for segment in late), code


def test_every_first_departure_is_0600_to_2155_local_on_its_day() -> None:
    minutes = set()
    for a, b in routes(1):
        for day in (DAY, DAY + 1):
            for _, segments, _ in world.day_flights(a, b, day):
                first = segments[0]
                assert first.depart_local[:10] == date_of(day)
                assert world.FIRST_DEPARTURE <= local_minute(first) <= world.LAST_DEPARTURE - 5
                assert local_minute(first) % 5 == 0
                minutes.add(local_minute(first))
    assert min(minutes) == 6 * 60 and max(minutes) == 21 * 60 + 55


def test_the_largest_search_stays_small() -> None:
    largest = max(len(json.dumps([plain_output(o) for o in world.trip_offers(a, b, DAY, DAY + 3)]))
                  for a, b in routes(1))
    print(f"largest search: {largest} characters")
    assert largest < LARGEST_SEARCH_CHARS


def test_every_round_trip_is_one_airline_both_ways_and_premium_costs_more_than_its_economy() -> None:
    for a, b in routes(5):
        offers = world.trip_offers(a, b, DAY, DAY + 3)
        for offer in offers:
            if offer.ticket is TicketType.ROUND_TRIP:
                codes = {segment.flight_number[:2] for segment in offer.outbound + offer.inbound}
                assert len(codes) == 1
        for offer in offers:
            if offer.ticket is TicketType.ROUND_TRIP and (offer.refundable or offer.cabin is not Cabin.ECONOMY):
                base = next(o for o in offers if o.carrier == offer.carrier and o.ticket is TicketType.ROUND_TRIP
                            and o.cabin is Cabin.ECONOMY and not o.refundable)
                assert offer.fare_cents > base.fare_cents


def test_the_world_holds_every_kind_of_trap() -> None:
    kinds = set()
    for a, b in routes(2):
        for offer in world.trip_offers(a, b, DAY, DAY + 3):
            kinds.add((offer.ticket, offer.cabin, offer.refundable))
    assert (TicketType.TWO_ONE_WAYS, Cabin.ECONOMY, False) in kinds
    assert (TicketType.ROUND_TRIP, Cabin.ECONOMY, True) in kinds
    assert (TicketType.ROUND_TRIP, Cabin.FIRST, False) in kinds
    assert (TicketType.ROUND_TRIP, Cabin.BUSINESS, False) in kinds or (TicketType.ROUND_TRIP, Cabin.BUSINESS, True) in kinds


def test_a_search_returns_a_fresh_copy(tmp_path: Path) -> None:
    first = world.trip_offers("IAH", "DEN", DAY, DAY + 3)
    first[0].outbound[0].depart = "edited"
    assert world.trip_offers("IAH", "DEN", DAY, DAY + 3)[0].outbound[0].depart != "edited"


def test_the_answer_key_agrees_with_an_independent_reading(tmp_path: Path) -> None:
    refusals = set()
    for index, value in enumerate(requests(500, "oracle")):
        key = solve_booking(value, tmp_path / str(index))
        miles = world.driving_miles(value.tda_airport.value, value.home_airport.value)
        refusal, correct = visit_answer(value, TODAY, miles, key.offers)
        assert (key.refusal.value, set(key.correct_offer_ids)) == (refusal, correct), index
        refusals.add(refusal)
    assert refusals >= {"NONE", "NOT_A_TDA", "NO_DUPLICATE_HOUSING", "ACCOMPANIED", "NO_MANAGER_APPROVAL",
                        "UNDER_400_MILES", "OUTSIDE_ASSIGNMENT", "TOO_SOON", "UNDER_14_DAYS_ADVANCE"}


def test_the_cheapest_offer_is_often_not_the_answer(tmp_path: Path) -> None:
    """The traps matter: on many bookable visits the cheapest offer of all is not compliant."""
    trapped = 0
    for index, value in enumerate(requests(300, "traps")):
        key = solve_booking(value, tmp_path / str(index))
        if key.refusal.value == "NONE" and min(o.fare_cents for o in key.offers) < key.lowest_fare_cents:
            trapped += 1
    assert trapped >= 5


def test_search_and_answer_key_see_the_same_offers(tmp_path: Path) -> None:
    value = next(requests(1, "same"))
    key = solve_booking(value, tmp_path)
    found = search_flights(SearchInput("", value.tda_airport, value.home_airport, value.outbound_date,
                                       value.return_date), tmp_path)
    assert [plain_output(o) for o in found.offers] == [plain_output(o) for o in key.offers]
    assert receipts.CLOCK()[:10] == TODAY

"""The verifier on correct, wrong, missing, malformed, tampered and boundary results, built the way the
sandbox builds them (build_output of plain JSON). Real simulated offers where they show the case, and
hand-built offers or distances (in the tools and the verifier alike) for exact boundaries."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from helpers import Run, booking, failed, hand_built, judge, offer, request, requests, tool_input
from slimconfig import build_output, plain_output

import verifier
from contract import (
    AirportCode,
    RequirementsInput,
    RequirementsOutput,
    SearchInput,
    SearchOutput,
    SolveOutput,
    Topic,
    TripOutput,
)
from plugin import booking_requirements, get_trip, search_flights, solve_booking

TRIP_REFUSALS = ("NOT_A_TDA", "NO_DUPLICATE_HOUSING", "ACCOMPANIED", "NO_MANAGER_APPROVAL", "UNDER_400_MILES",
                 "OUTSIDE_ASSIGNMENT", "TOO_SOON", "UNDER_14_DAYS_ADVANCE")


def valid(verdict: dict) -> bool:
    return verdict["valid"] is True and verdict["score"] == 1.0


def refused(verdict: dict, *check_ids: str) -> bool:
    return verdict["valid"] is False and verdict["score"] == 0.0 and failed(verdict) == list(check_ids)


# Correct --------------------------------------------------------------------------------------------


def test_the_gold_answer_is_valid_for_varied_requests(tmp_path: Path) -> None:
    seen = set()
    for index, value in enumerate(requests(150, "gold")):
        run = Run(value, tmp_path / str(index))
        verdict = run.judge(run.gold())
        assert valid(verdict), (plain_output(value), verdict["message"])
        assert all(entry["ok"] is True for entry in verdict["details"]["checks"])
        seen.add(run.key.refusal.value)
    assert seen >= {"NONE", *TRIP_REFUSALS}


def test_exactly_the_correct_offers_pass(tmp_path: Path) -> None:
    """Every offer the agent could book from its search is judged: valid if and only if the answer key
    lists it as correct (ties included)."""
    judged = 0
    for index, value in enumerate(requests(300, "every-offer")):
        run = Run(value, tmp_path / str(index))
        if run.key.refusal.value != "NONE":
            continue
        for found in run.offers:
            verdict = run.judge(booking(run.run_id, found.offer_id))
            assert verdict["valid"] is (found.offer_id in run.key.correct_offer_ids), (index, found.offer_id)
            judged += 1
    assert judged > 200


@pytest.mark.parametrize("refusal", TRIP_REFUSALS)
def test_a_refusal_by_the_visit_needs_no_search(tmp_path: Path, refusal: str) -> None:
    value = next(v for v in requests(2000, f"refuse-{refusal}") if solve_booking(v, tmp_path / "k").refusal.value == refusal)
    run = Run(value, tmp_path / "run", search=False)
    assert valid(run.judge(booking(run.run_id, booked=False, refusal=refusal)))


# Wrong ------------------------------------------------------------------------------------------------


def bookable(tmp_path: Path, test=lambda key: True, salt: str = "bookable") -> Run:
    """A run of the first varied request that must be booked and whose key passes ``test``."""
    for index, value in enumerate(requests(3000, salt)):
        key = solve_booking(value, tmp_path / "keys" / str(index))
        if key.refusal.value == "NONE" and test(key):
            return Run(value, tmp_path / "run")
    raise LookupError(salt)


@pytest.mark.parametrize(
    ("pick", "check_id"),
    [
        (lambda o: o.ticket.value == "TWO_ONE_WAYS", "ticket"),
        (lambda o: o.ticket.value == "ROUND_TRIP" and o.cabin.value != "ECONOMY", "cabin"),
        (lambda o: o.ticket.value == "ROUND_TRIP" and o.cabin.value == "ECONOMY" and o.refundable, "refundable"),
    ],
    ids=["two-one-ways", "premium-cabin", "refundable"],
)
def test_a_non_compliant_fare_is_refused(tmp_path: Path, pick, check_id: str) -> None:
    run = bookable(tmp_path, lambda key: any(pick(o) for o in key.offers), f"wrong-{check_id}")
    chosen = next(o for o in run.offers if pick(o))
    assert refused(run.judge(booking(run.run_id, chosen.offer_id)), check_id)


def test_a_dearer_compliant_fare_is_refused(tmp_path: Path) -> None:
    run = bookable(tmp_path, lambda key: len(key.compliant_offer_ids) > len(key.correct_offer_ids), "dearer")
    dearer = next(i for i in run.key.compliant_offer_ids if i not in run.key.correct_offer_ids)
    verdict = run.judge(booking(run.run_id, dearer))
    assert refused(verdict, "fare") and "lowest" in verdict["message"]


@pytest.mark.parametrize("refusal", [*TRIP_REFUSALS, "NO_COMPLIANT_FLIGHT"])
def test_refusing_a_bookable_visit_is_refused(tmp_path: Path, refusal: str) -> None:
    run = bookable(tmp_path)
    assert refused(run.judge(booking(run.run_id, booked=False, refusal=refusal)), "refusal")


def test_booking_a_refused_visit_is_refused(tmp_path: Path) -> None:
    run = Run(request(manager_approved=False), tmp_path)
    verdict = run.judge(booking(run.run_id, run.offers[0].offer_id))
    assert refused(verdict, "refusal") and "manager" in verdict["message"]


def test_the_wrong_refusal_reason_is_refused(tmp_path: Path) -> None:
    run = Run(request(family_status="ACCOMPANIED", manager_approved=False), tmp_path, search=False)
    assert valid(run.judge(booking(run.run_id, booked=False, refusal="ACCOMPANIED")))
    assert refused(run.judge(booking(run.run_id, booked=False, refusal="NO_MANAGER_APPROVAL")), "refusal")


@pytest.mark.parametrize(
    "changes",
    [{"booked": True, "refusal": "TOO_SOON"}, {"booked": False, "refusal": "NONE"},
     {"booked": False, "refusal": "TOO_SOON", "offer_id": "x"}],
)
def test_an_inconsistent_answer_is_refused(tmp_path: Path, changes: dict) -> None:
    run = Run(request(last_home_visit="2026-11-20"), tmp_path)
    output = booking(run.run_id, run.offers[0].offer_id) | changes
    assert refused(run.judge(output), "refusal")


def test_an_offer_on_other_days_is_refused(tmp_path: Path) -> None:
    run = Run(request(), tmp_path)
    other = run.search(return_date="2026-12-08").offers
    assert refused(run.judge(booking(run.run_id, other[0].offer_id)), "dates")


def test_an_offer_on_another_route_is_refused(tmp_path: Path) -> None:
    run = Run(request(), tmp_path)
    other = run.search(destination="ORD").offers
    verdict = run.judge(booking(run.run_id, other[0].offer_id))
    assert refused(verdict, "offer-seen") and "IAH-ORD-IAH" in verdict["message"]


# Boundaries, on hand-built offers and distances -----------------------------------------------------------


@pytest.mark.parametrize(("miles", "ok"), [(400, True), (399, False)])
def test_exactly_400_miles_flies_and_399_drives(tmp_path: Path, miles: int, ok: bool) -> None:
    with hand_built([offer("20261204-20261207-01", 40_000)], miles=miles):
        run = Run(request(), tmp_path)
        assert valid(run.judge(booking(run.run_id, "20261204-20261207-01"))) is ok
        assert valid(run.judge(booking(run.run_id, booked=False, refusal="UNDER_400_MILES"))) is not ok


def test_tied_lowest_fares_both_pass_and_one_cent_more_fails(tmp_path: Path) -> None:
    offers = [offer("20261204-20261207-01", 40_000), offer("20261204-20261207-02", 40_000),
              offer("20261204-20261207-03", 40_001), offer("20261204-20261207-04", 39_000, refundable=True),
              offer("20261204-20261207-05", 38_000, ticket="TWO_ONE_WAYS")]
    with hand_built(offers):
        run = Run(request(), tmp_path)
        assert valid(run.judge(booking(run.run_id, "20261204-20261207-01")))
        assert valid(run.judge(booking(run.run_id, "20261204-20261207-02")))
        assert refused(run.judge(booking(run.run_id, "20261204-20261207-03")), "fare")
        assert refused(run.judge(booking(run.run_id, "20261204-20261207-04")), "refundable")
        assert refused(run.judge(booking(run.run_id, "20261204-20261207-05")), "ticket")


def test_only_non_compliant_fares_means_no_compliant_flight(tmp_path: Path) -> None:
    offers = [offer("20261204-20261207-01", 30_000, refundable=True), offer("20261204-20261207-02", 50_000,
                                                                             cabin="FIRST")]
    with hand_built(offers):
        run = Run(request(), tmp_path)
        assert valid(run.judge(booking(run.run_id, booked=False, refusal="NO_COMPLIANT_FLIGHT")))
        assert refused(run.judge(booking(run.run_id, "20261204-20261207-02")), "refusal")


def test_no_compliant_flight_needs_a_search(tmp_path: Path) -> None:
    with hand_built([]):
        run = Run(request(), tmp_path, search=False)
        assert refused(run.judge(booking(run.run_id, booked=False, refusal="NO_COMPLIANT_FLIGHT")), "searched")


# Missing ------------------------------------------------------------------------------------------------


def test_booking_without_a_search_is_refused(tmp_path: Path) -> None:
    run = Run(request(), tmp_path, search=False)
    assert refused(run.judge(booking(run.run_id, run.key.correct_offer_ids[0])), "searched")


@pytest.mark.parametrize("offer_id", ["20261204-20261207-99", "", "F01"])
def test_an_offer_never_returned_is_refused(tmp_path: Path, offer_id: str) -> None:
    run = Run(request(), tmp_path)
    assert refused(run.judge(booking(run.run_id, offer_id)), "offer-seen")


@pytest.mark.parametrize("run_id", ["0123456789ab", "not-a-run", ""])
def test_a_run_that_does_not_exist_is_refused(tmp_path: Path, run_id: str) -> None:
    run = Run(request(), tmp_path)
    assert refused(run.judge(booking(run_id, run.key.correct_offer_ids[0])), "this-run")


def test_no_answer_key_is_refused(tmp_path: Path) -> None:
    run = Run(request(), tmp_path)
    assert refused(judge(run.request, run.gold(), None, run.workspace), "answer-key")


# Tampered -------------------------------------------------------------------------------------------------


def test_an_answer_key_for_another_request_is_refused(tmp_path: Path) -> None:
    run = Run(request(), tmp_path)
    other = solve_booking(request(return_date="2026-12-08"), tmp_path / "other")
    assert refused(judge(run.request, run.gold(), other, run.workspace), "answer-key")


def test_a_tampered_answer_key_is_refused(tmp_path: Path) -> None:
    run = Run(request(), tmp_path)
    for changes in ({"correct_offer_ids": [run.offers[-1].offer_id]}, {"refusal": "TOO_SOON"},
                    {"lowest_fare_cents": 1}):
        key = build_output(plain_output(run.key) | changes, SolveOutput)
        assert refused(judge(run.request, run.gold(), key, run.workspace), "answer-key")


def test_an_answer_key_with_edited_offers_or_trip_is_refused(tmp_path: Path) -> None:
    run = Run(request(), tmp_path)
    plain = plain_output(run.key)
    plain["offers"][0]["fare_cents"] += 1
    assert refused(judge(run.request, run.gold(), build_output(plain, SolveOutput), run.workspace), "answer-key")
    plain = plain_output(run.key)
    plain["trip"]["estimated_driving_miles"] = 300
    assert refused(judge(run.request, run.gold(), build_output(plain, SolveOutput), run.workspace), "answer-key")


@pytest.mark.parametrize("changes", [{"digest": "0" * 64}, {"offer_ids": []}, {"origin": "XXX"}, {"return_date": "x"},
                                     {"origin": None}])
def test_a_tampered_search_receipt_is_refused(tmp_path: Path, changes: dict) -> None:
    run = Run(request(), tmp_path)
    path = run.workspace / "runs" / run.run_id / "search-1.json"
    path.write_text(json.dumps(json.loads(path.read_text()) | changes))
    assert refused(run.judge(run.gold()), "receipts-match")


def test_a_run_begun_before_the_answer_key_is_refused(tmp_path: Path) -> None:
    value = request()
    early = get_trip(value, tmp_path / "workspace")
    run = Run(value, tmp_path)
    run.run_id = early.run_id
    run.search()
    assert refused(run.judge(run.gold()), "this-run")


def test_a_run_booked_on_another_day_is_refused(tmp_path: Path) -> None:
    run = Run(request(), tmp_path)
    path = run.workspace / "runs" / run.run_id / "trip.json"
    path.write_text(json.dumps(json.loads(path.read_text()) | {"booking_date": "2026-11-04"}))
    assert refused(run.judge(run.gold()), "this-run")


def test_a_run_of_another_request_is_refused(tmp_path: Path) -> None:
    run = Run(request(), tmp_path)
    other = get_trip(request(traveller_name="Someone Else"), run.workspace)
    assert refused(run.judge(run.gold() | {"run_id": other.run_id}), "this-run")


def test_the_verdict_is_the_same_twice(tmp_path: Path) -> None:
    run = Run(request(), tmp_path)
    assert run.judge(run.gold()) == run.judge(run.gold())


# Tool inputs and outputs ------------------------------------------------------------------------------------


def test_tool_inputs_are_checked() -> None:
    from helpers import plain_request

    assert tool_input("get_trip", plain_request())["valid"] is True
    assert tool_input("solve_booking", plain_request())["valid"] is True
    for changes in ({"home_airport": "IAH"}, {"outbound_date": "2026-12-32"}, {"return_date": "2026-12-01"},
                    {"last_home_visit": "2026-12-05"}, {"assignment_end": "2026-01-01"}, {"traveller_name": ""}):
        assert tool_input("get_trip", plain_request(**changes))["valid"] is False, changes
    search = {"run_id": "", "origin": "IAH", "destination": "DEN", "outbound_date": "2026-12-04",
              "return_date": "2026-12-07"}
    assert tool_input("search_flights", search)["valid"] is True
    for changes in ({"destination": "IAH"}, {"return_date": "2026-12-03"}, {"return_date": "2027-01-04"},
                    {"run_id": "nope"}, {"outbound_date": "x"}):
        assert tool_input("search_flights", search | changes)["valid"] is False, changes
    assert tool_input("booking_requirements", {"topic": "ALL"})["valid"] is True


def test_tool_outputs_are_checked(tmp_path: Path) -> None:
    run = Run(request(), tmp_path)
    started = plain_output(TripOutput(run.run_id, run.trip))
    check = verifier.verify_output("get_trip", run.request, build_output(started, TripOutput), str(run.workspace))
    assert check["valid"] is True
    started["trip"]["days_since_previous_visit"] += 1
    assert verifier.verify_output("get_trip", run.request, build_output(started, TripOutput),
                                  str(run.workspace))["valid"] is False
    query = SearchInput(run.run_id, AirportCode.IAH, AirportCode.DEN, "2026-12-04", "2026-12-07")
    found = plain_output(search_flights(query, run.workspace))
    assert verifier.verify_output("search_flights", query, build_output(found, SearchOutput), "")["valid"] is True
    found["offers"][0]["refundable"] = not found["offers"][0]["refundable"]
    assert verifier.verify_output("search_flights", query, build_output(found, SearchOutput), "")["valid"] is False
    key = plain_output(run.key)
    assert verifier.verify_output("solve_booking", run.request, build_output(key, SolveOutput), "")["valid"] is True


@pytest.mark.parametrize("topic", list(Topic))
def test_the_requirements_are_checked(tmp_path: Path, topic: Topic) -> None:
    answer = plain_output(booking_requirements(RequirementsInput(topic), tmp_path))
    query = RequirementsInput(topic)
    assert verifier.verify_output("booking_requirements", query, build_output(answer, RequirementsOutput), "")["valid"]
    answer["example_request"] = "Book anything."
    assert not verifier.verify_output("booking_requirements", query, build_output(answer, RequirementsOutput), "")["valid"]


def test_tool_tasks_are_judged_as_their_tools(tmp_path: Path) -> None:
    query = SearchInput("", AirportCode.IAH, AirportCode.DEN, "2026-12-04", "2026-12-07")
    found = search_flights(query, tmp_path)
    assert verifier.verify_task("search-flights", query, found, None, str(tmp_path))["valid"] is True
    answer = booking_requirements(RequirementsInput(Topic.AIRPORTS), tmp_path)
    assert verifier.verify_task("booking-requirements", RequirementsInput(Topic.AIRPORTS), answer, None, "")["valid"]


def test_tools_refuse_past_and_far_dates(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="past"):
        get_trip(request(outbound_date="2026-11-04", return_date="2026-11-06", last_home_visit=""), tmp_path)
    with pytest.raises(ValueError, match="far ahead"):
        search_flights(SearchInput("", AirportCode.IAH, AirportCode.DEN, "2027-09-30", "2027-10-02"), tmp_path)
    with pytest.raises(ValueError, match="get_trip"):
        search_flights(SearchInput("0123456789ab", AirportCode.IAH, AirportCode.DEN, "2026-12-04", "2026-12-07"),
                       tmp_path)

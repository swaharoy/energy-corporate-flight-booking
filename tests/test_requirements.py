"""booking_requirements, read independently of the tool's own code: every field of the booking task's input
is named, described as the contract describes it, and has an example the input accepts; every airport is
listed; nothing about the policy is asked of the traveller."""

from __future__ import annotations

import dataclasses
import typing
from pathlib import Path

import pytest
from conftest import TODAY
from helpers import tool_input
from slimconfig import build_output

from contract import AirportCode, RequirementsInput, Topic, TripInput
from plugin import booking_requirements, solve_booking, world


@pytest.fixture
def everything(tmp_path: Path):
    return booking_requirements(RequirementsInput(Topic.ALL), tmp_path)


def example(everything) -> dict:
    value = {field.name: field.example for field in everything.fields}
    for name in ("duplicate_housing_obligation", "manager_approved"):
        value[name] = value[name] == "true"
    return value


def test_every_input_field_is_named_and_described_as_the_contract_says(everything) -> None:
    hints = typing.get_type_hints(TripInput, include_extras=True)
    assert [field.name for field in everything.fields] == [field.name for field in dataclasses.fields(TripInput)]
    for field in everything.fields:
        assert field.required is (field.name != "last_home_visit")
        assert field.description == typing.get_args(hints[field.name])[1]


def test_the_examples_make_a_request_the_booking_task_accepts_and_books(everything, tmp_path: Path) -> None:
    value = example(everything)
    assert tool_input("get_trip", value)["valid"] is True
    for name in ("assignment_start", "assignment_end", "last_home_visit", "outbound_date", "return_date"):
        assert value[name] in everything.example_request
    key = solve_booking(build_output(value, TripInput), tmp_path)
    assert key.refusal.value == "NONE"


def test_every_airport_is_listed(everything) -> None:
    assert [airport.code for airport in everything.airports] == [member.value for member in AirportCode]
    assert everything.airports[0].city == world.airport("ATL").city


def test_the_date_rules_state_today_and_the_limits(everything) -> None:
    assert everything.today == TODAY
    text = " ".join(everything.date_rules)
    assert TODAY in text and "30 days" in text and "330 days" in text and "2027-10-01" in text


def test_no_policy_is_asked_of_the_traveller(everything) -> None:
    text = " ".join([everything.example_request, *everything.date_rules]).lower()
    for word in ("400", "refundable", "economy", "four weeks", "two weeks", "advance", "policy", "cheapest", "lowest"):
        assert word not in text


@pytest.mark.parametrize(("topic", "fields", "airports"), [(Topic.FIELDS, True, False), (Topic.AIRPORTS, False, True)])
def test_a_topic_narrows_the_answer(tmp_path: Path, topic: Topic, fields: bool, airports: bool) -> None:
    answer = booking_requirements(RequirementsInput(topic), tmp_path)
    assert bool(answer.fields) is fields and bool(answer.date_rules) is fields and bool(answer.airports) is airports

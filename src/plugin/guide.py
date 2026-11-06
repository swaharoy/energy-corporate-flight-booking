"""What a home-visit request must give, shared byte for byte by the booking_requirements tool
(src/plugin/guide.py) and the verifier (verifier/guide.py): every field of the booking task's input, read
from the contract, with an example; the date rules; and the airports. No policy: applying the policy is
the agent's job, not the traveller's. It imports only modules a verifier may use, contract, and its
package's shared modules.
"""

import dataclasses
import enum
import typing

from contract import AirportCode, AirportHelp, FieldHelp, RequirementsOutput, Topic, TripInput

from .rules import BOOKING_HORIZON_DAYS, LONGEST_VISIT_DAYS, date_of, day_number
from .world import AIRPORTS

DATE_FIELDS = ("assignment_start", "assignment_end", "last_home_visit", "outbound_date", "return_date")


def example_dates(today):
    """(assignment start, assignment end, last home visit, outbound, return) around ``today``."""
    now = day_number(today)
    return (date_of(now - 60), date_of(now + 120), date_of(now - 10), date_of(now + 30), date_of(now + 33))


def examples(today):
    start, end, last, outbound, back = example_dates(today)
    return {
        "traveller_name": "Jordan Lee",
        "tda_airport": "IAH",
        "home_airport": "DEN",
        "assignment_start": start,
        "assignment_end": end,
        "family_status": "SINGLE",
        "duplicate_housing_obligation": "true",
        "last_home_visit": last,
        "manager_approved": "true",
        "outbound_date": outbound,
        "return_date": back,
    }


def kind_of(name, kind):
    """What kind of value a field takes, in words."""
    if kind is bool:
        return "yes or no (true or false)"
    if isinstance(kind, type) and issubclass(kind, AirportCode):
        return f"an airport code from the airport list ({len(AIRPORTS)} U.S. airports)"
    if isinstance(kind, type) and issubclass(kind, enum.Enum):
        return "one of " + ", ".join(member.value for member in kind)
    if name == "last_home_visit":
        return "a date, YYYY-MM-DD, or empty when there was no home visit yet"
    if name in DATE_FIELDS:
        return "a date, YYYY-MM-DD"
    return "text"


def fields(today):
    """Every field of the booking task's input, in the contract's order."""
    hints = typing.get_type_hints(TripInput, include_extras=True)
    example = examples(today)
    found = []
    for field in dataclasses.fields(TripInput):
        kind, description = typing.get_args(hints[field.name])
        found.append(FieldHelp(name=field.name, kind=kind_of(field.name, kind), required=field.name != "last_home_visit",
                               example=example[field.name], description=description))
    return found


def date_rules(today):
    last = date_of(day_number(today) + BOOKING_HORIZON_DAYS)
    return [
        f"Today is {today} (UTC): a request made today is booked as of today.",
        "Dates are YYYY-MM-DD.",
        (
            "Flight dates are local dates at the airport the flight leaves from: outbound_date at the assignment "
            "airport, return_date at the home airport. Flights leave from 06:00 to 21:55 local time."
        ),
        "The assignment dates and the last home visit may be in the past; the flights may not.",
        "outbound_date is the day to fly home; return_date the day to fly back to the assignment.",
        f"return_date is on or after outbound_date, at most {LONGEST_VISIT_DAYS} days later.",
        (
            f"Flights are sold from today up to {BOOKING_HORIZON_DAYS} days ahead: outbound_date is {today} or "
            f"later, and return_date is {last} or earlier."
        ),
        "Leave last_home_visit empty when there has been no home visit yet during this assignment.",
    ]


def airports():
    return [AirportHelp(code=row[0], name=row[1], city=row[2]) for row in AIRPORTS]


def example_request(today):
    start, end, last, outbound, back = example_dates(today)
    return (
        f"Book a home visit for Jordan Lee, on a temporary assignment in Houston (IAH) from {start} to {end}. "
        f"Jordan is single, still keeps their home in Denver (DEN), last went home on {last}, and their "
        f"manager approved this visit: fly home on {outbound} and back on {back}."
    )


def build(topic, today):
    """The requirements for ``topic`` as of ``today``."""
    wants_fields = topic in (Topic.ALL, Topic.FIELDS)
    wants_airports = topic in (Topic.ALL, Topic.AIRPORTS)
    return RequirementsOutput(
        today=today,
        fields=fields(today) if wants_fields else [],
        date_rules=date_rules(today) if wants_fields else [],
        airports=airports() if wants_airports else [],
        example_request=example_request(today),
    )

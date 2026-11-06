"""Each tool's and task's typed input and output (see nanoagent.plugin.v0001.contract): declarations only."""

from dataclasses import dataclass
from enum import Enum
from typing import Annotated

from slimconfig import Output


class Tool(Enum):
    BOOKING_REQUIREMENTS = "booking_requirements"
    GET_TRIP = "get_trip"
    SEARCH_FLIGHTS = "search_flights"
    SOLVE_BOOKING = "solve_booking"


class Task(Enum):
    BOOKING_REQUIREMENTS = "booking-requirements"
    SEARCH_FLIGHTS = "search-flights"
    BOOK_FLIGHT = "energy-corporate-flight-booking"


class FamilyStatus(Enum):
    SINGLE = "SINGLE"
    UNACCOMPANIED = "UNACCOMPANIED"
    ACCOMPANIED = "ACCOMPANIED"


class AirportCode(Enum):
    """The U.S. airports this plugin knows, by IATA code (booking_requirements lists their names and cities)."""

    ATL = "ATL"
    LAX = "LAX"
    ORD = "ORD"
    DFW = "DFW"
    DEN = "DEN"
    JFK = "JFK"
    SFO = "SFO"
    SEA = "SEA"
    LAS = "LAS"
    MCO = "MCO"
    EWR = "EWR"
    MIA = "MIA"
    CLT = "CLT"
    PHX = "PHX"
    IAH = "IAH"
    BOS = "BOS"
    MSP = "MSP"
    DTW = "DTW"
    PHL = "PHL"
    LGA = "LGA"
    BWI = "BWI"
    SLC = "SLC"
    SAN = "SAN"
    IAD = "IAD"
    DCA = "DCA"
    TPA = "TPA"
    AUS = "AUS"
    BNA = "BNA"
    HNL = "HNL"
    ANC = "ANC"
    STL = "STL"


class Cabin(Enum):
    ECONOMY = "ECONOMY"
    BUSINESS = "BUSINESS"
    FIRST = "FIRST"


class TicketType(Enum):
    ROUND_TRIP = "ROUND_TRIP"
    TWO_ONE_WAYS = "TWO_ONE_WAYS"


class Refusal(Enum):
    NONE = "NONE"
    NOT_A_TDA = "NOT_A_TDA"
    NO_DUPLICATE_HOUSING = "NO_DUPLICATE_HOUSING"
    ACCOMPANIED = "ACCOMPANIED"
    NO_MANAGER_APPROVAL = "NO_MANAGER_APPROVAL"
    UNDER_400_MILES = "UNDER_400_MILES"
    OUTSIDE_ASSIGNMENT = "OUTSIDE_ASSIGNMENT"
    TOO_SOON = "TOO_SOON"
    UNDER_14_DAYS_ADVANCE = "UNDER_14_DAYS_ADVANCE"
    NO_COMPLIANT_FLIGHT = "NO_COMPLIANT_FLIGHT"


class Topic(Enum):
    ALL = "ALL"
    FIELDS = "FIELDS"
    AIRPORTS = "AIRPORTS"


RUN_ID = "This booking run's id, as get_trip returned it"
TIME = "A UTC time, YYYY-MM-DD HH:MM"
CODE = "An IATA airport code, e.g. IAH"


@dataclass
class Airport(Output):
    code: Annotated[str, CODE]
    name: Annotated[str, "The airport's name"]
    city: Annotated[str, "The city it serves"]


@dataclass
class Trip(Output):
    traveller_name: Annotated[str, "The traveller's name"]
    tda: Annotated[Airport, "The airport at the temporary assignment location, where the visit starts and ends"]
    home: Annotated[Airport, "The airport at the traveller's primary residence"]
    assignment_start: Annotated[str, "The assignment's first day, YYYY-MM-DD"]
    assignment_end: Annotated[str, "The assignment's last day, YYYY-MM-DD"]
    assignment_days: Annotated[int, "The assignment's length in days, first and last day included"]
    family_status: Annotated[FamilyStatus, "SINGLE, UNACCOMPANIED or ACCOMPANIED"]
    duplicate_housing_obligation: Annotated[bool, "Whether the traveller still keeps their primary residence"]
    manager_approved: Annotated[bool, "Whether the traveller's manager approved this home visit"]
    last_home_visit: Annotated[str, "The day the last home visit left, YYYY-MM-DD; empty when there was none"]
    days_since_previous_visit: Annotated[
        int, "Days from the last home visit (the assignment start when there was none) to outbound_date"
    ]
    outbound_date: Annotated[str, "The day to fly home, YYYY-MM-DD, the local date at the tda airport"]
    return_date: Annotated[str, "The day to fly back to the assignment, YYYY-MM-DD, the local date at the home airport"]
    booking_date: Annotated[str, "Today, the day the flight is booked, YYYY-MM-DD (UTC)"]
    days_before_departure: Annotated[int, "Days from booking_date to outbound_date (the local departure date)"]
    estimated_driving_miles: Annotated[
        int, "The estimated driving distance between the two locations: great-circle miles between the airports x 1.2"
    ]


@dataclass
class Segment(Output):
    origin: Annotated[str, CODE]
    destination: Annotated[str, CODE]
    flight_number: Annotated[str, "The airline's flight number, e.g. UA 1482"]
    depart: Annotated[str, TIME]
    arrive: Annotated[str, TIME]
    depart_local: Annotated[str, "When it leaves, YYYY-MM-DD HH:MM local time at its origin airport"]
    air_minutes: Annotated[int, "Minutes in the air"]


@dataclass
class Offer(Output):
    offer_id: Annotated[str, "The offer's id: its outbound and return dates and number, e.g. 20261204-20261207-03"]
    carrier: Annotated[str, "The airline, or both airlines of two one-way tickets"]
    ticket: Annotated[TicketType, "ROUND_TRIP: one round-trip ticket; TWO_ONE_WAYS: two separate one-way tickets"]
    cabin: Annotated[Cabin, "The cabin class, both ways"]
    refundable: Annotated[bool, "Whether the fare is refundable"]
    fare_cents: Annotated[int, "The total fare for both directions, in cents"]
    outbound: Annotated[list[Segment], "The flights home, in order"]
    inbound: Annotated[list[Segment], "The flights back to the assignment, in order"]


@dataclass
class TripInput(Output):
    traveller_name: Annotated[str, "The traveller's full name, as on the ticket"]
    tda_airport: Annotated[AirportCode, "The airport at the temporary assignment location (e.g. IAH for Houston)"]
    home_airport: Annotated[AirportCode, "The airport at the traveller's primary residence (e.g. DEN for Denver)"]
    assignment_start: Annotated[str, "The temporary assignment's first day, YYYY-MM-DD"]
    assignment_end: Annotated[str, "The temporary assignment's last day, YYYY-MM-DD"]
    family_status: Annotated[
        FamilyStatus,
        "SINGLE (unmarried, no dependents), UNACCOMPANIED (spouse or partner stays at home) or ACCOMPANIED "
        "(family joins the traveller at the assignment)",
    ]
    duplicate_housing_obligation: Annotated[
        bool, "Whether the traveller still keeps (leases or owns) their primary residence during the assignment"
    ]
    last_home_visit: Annotated[
        str, "The day the traveller last left on a home visit during this assignment, YYYY-MM-DD; empty if none yet"
    ]
    manager_approved: Annotated[bool, "Whether the traveller's manager approved this home visit"]
    outbound_date: Annotated[
        str, "The day to fly home, YYYY-MM-DD, today or later: the local date at the assignment airport"
    ]
    return_date: Annotated[
        str, "The day to fly back to the assignment, YYYY-MM-DD, on or after outbound_date: the local date at home"
    ]


@dataclass
class TripOutput(Output):
    run_id: Annotated[str, "This booking run's id: pass it to search_flights and submit it"]
    trip: Annotated[Trip, "The home visit to book"]


@dataclass
class SearchInput(Output):
    run_id: Annotated[str, "This booking run's id, as get_trip returned it; empty to only look, outside a booking"]
    origin: Annotated[AirportCode, "The airport to leave from and come back to"]
    destination: Annotated[AirportCode, "The airport to fly to"]
    outbound_date: Annotated[str, "The day to fly out, YYYY-MM-DD, today or later: the local date at origin"]
    return_date: Annotated[
        str, "The day to fly back, YYYY-MM-DD, 0 to 30 days after outbound_date: the local date at destination"
    ]


@dataclass
class SearchOutput(Output):
    run_id: Annotated[str, RUN_ID]
    note: Annotated[str, "Where the offers come from: simulated fares and schedules"]
    offers: Annotated[
        list[Offer], "Every offer leaving origin on outbound_date and destination on return_date (local dates)"
    ]


@dataclass
class BookingOutput(Output):
    run_id: Annotated[str, RUN_ID]
    booked: Annotated[bool, "Whether a flight is booked"]
    refusal: Annotated[Refusal, "Why nothing is booked; NONE when a flight is booked"]
    offer_id: Annotated[str, "The booked offer's id; empty when nothing is booked"]


@dataclass
class SolveOutput(Output):
    pinned_at: Annotated[str, "When the answer key was pinned, UTC YYYY-MM-DD HH:MM:SS.ffffff"]
    trip: Annotated[Trip, "The trip, with today as its booking date"]
    offers: Annotated[list[Offer], "Every offer out on the outbound date and back on the return date"]
    refusal: Annotated[Refusal, "The correct refusal, NONE when a flight must be booked"]
    compliant_offer_ids: Annotated[list[str], "The round-trip, economy, non-refundable offers"]
    lowest_fare_cents: Annotated[int, "The lowest compliant fare; 0 when nothing is booked"]
    correct_offer_ids: Annotated[list[str], "Every offer that is a correct booking"]


@dataclass
class RequirementsInput(Output):
    topic: Annotated[Topic, "ALL for everything, FIELDS for what to tell us, AIRPORTS for the airport list"]


@dataclass
class FieldHelp(Output):
    name: Annotated[str, "The field's name"]
    kind: Annotated[str, "What kind of value it takes"]
    required: Annotated[bool, "Whether every booking request must give it"]
    example: Annotated[str, "An example value"]
    description: Annotated[str, "What it means"]


@dataclass
class AirportHelp(Output):
    code: Annotated[str, CODE]
    name: Annotated[str, "The airport's name"]
    city: Annotated[str, "The city it serves"]


@dataclass
class RequirementsOutput(Output):
    today: Annotated[str, "Today, the booking date, YYYY-MM-DD (UTC)"]
    fields: Annotated[list[FieldHelp], "What a booking request gives, field by field; empty for AIRPORTS"]
    date_rules: Annotated[list[str], "How the dates work; empty for AIRPORTS"]
    airports: Annotated[list[AirportHelp], "The airports a trip may use; empty for FIELDS"]
    example_request: Annotated[str, "A complete booking request in plain words"]


TOOLS = {
    Tool.BOOKING_REQUIREMENTS: (RequirementsInput, RequirementsOutput),
    Tool.GET_TRIP: (TripInput, TripOutput),
    Tool.SEARCH_FLIGHTS: (SearchInput, SearchOutput),
    Tool.SOLVE_BOOKING: (TripInput, SolveOutput),
}
TASKS = {
    Task.BOOKING_REQUIREMENTS: (RequirementsInput, RequirementsOutput),
    Task.SEARCH_FLIGHTS: (SearchInput, SearchOutput),
    Task.BOOK_FLIGHT: (TripInput, BookingOutput),
}

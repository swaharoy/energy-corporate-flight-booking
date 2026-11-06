"""The energy company's return-home-visit rules, shared byte for byte by the tools (src/plugin/rules.py) and
the verifier (verifier/rules.py): dates, what a visit request may be, the refusal or booking the rules
require, and the canonical form of requests and offers both sides compare.

Exact integer arithmetic only, and no datetime (a verifier may not import it): a date is a day number.
It imports only modules a verifier may use, and contract.
"""

import hashlib
import json
import re
from dataclasses import dataclass

from contract import Cabin, FamilyStatus, Refusal, TicketType

DATE = re.compile(r"^(\d{4})-(\d{2})-(\d{2})$")
TIME = re.compile(r"^(\d{4}-\d{2}-\d{2}) (\d{2}):(\d{2})$")
TDA_MIN_DAYS, TDA_MAX_DAYS = 91, 365  # a temporary domestic assignment lasts 91 to 365 days
AIRFARE_MILES = 400  # airfare only when the locations are this many miles apart or more
VISIT_GAP_DAYS = {FamilyStatus.SINGLE: 28, FamilyStatus.UNACCOMPANIED: 14}  # at most one visit per gap
ADVANCE_DAYS = 14  # home-visit airfare is a 14-day advance purchase
LONGEST_VISIT_DAYS = 30  # a visit (and one search) returns at most this many days after it leaves
BOOKING_HORIZON_DAYS = 330  # flights are sold up to this many days after today
NAME_MOST_CHARS = 80


def day_number(date):
    """Days since 1970-01-01 of a YYYY-MM-DD date; ValueError when it is not a real date."""
    match = DATE.fullmatch(date)
    if not match:
        raise ValueError(f"{date!r} is not a YYYY-MM-DD date")
    year, month, day = (int(part) for part in match.groups())
    if not 1 <= month <= 12 or not 1 <= day <= days_in_month(year, month):
        raise ValueError(f"{date!r} is not a real date")
    year -= month <= 2
    era = year // 400
    year_of_era = year - era * 400
    day_of_year = (153 * (month + (-3 if month > 2 else 9)) + 2) // 5 + day - 1
    day_of_era = year_of_era * 365 + year_of_era // 4 - year_of_era // 100 + day_of_year
    return era * 146097 + day_of_era - 719468


def date_of(number):
    """The YYYY-MM-DD date of a day number."""
    number += 719468
    era = number // 146097
    day_of_era = number - era * 146097
    year_of_era = (day_of_era - day_of_era // 1460 + day_of_era // 36524 - day_of_era // 146096) // 365
    day_of_year = day_of_era - (365 * year_of_era + year_of_era // 4 - year_of_era // 100)
    shifted = (5 * day_of_year + 2) // 153
    day = day_of_year - (153 * shifted + 2) // 5 + 1
    month = shifted + (3 if shifted < 10 else -9)
    year = year_of_era + era * 400 + (month <= 2)
    return f"{year:04d}-{month:02d}-{day:02d}"


def days_in_month(year, month):
    if month == 2:
        return 29 if year % 4 == 0 and (year % 100 != 0 or year % 400 == 0) else 28
    return 30 if month in (4, 6, 9, 11) else 31


def is_date(text):
    try:
        day_number(text)
    except ValueError:
        return False
    return True


def minute_number(time):
    """Minutes since 1970-01-01 00:00 of a YYYY-MM-DD HH:MM time; ValueError when it is not one."""
    match = TIME.fullmatch(time)
    if not match:
        raise ValueError(f"{time!r} is not a YYYY-MM-DD HH:MM time")
    date, hour, minute = match.group(1), int(match.group(2)), int(match.group(3))
    if hour > 23 or minute > 59:
        raise ValueError(f"{time!r} is not a real time")
    return day_number(date) * 1440 + hour * 60 + minute


def days_between(first, last):
    return day_number(last) - day_number(first)


def request_problem(request):
    """What is wrong with a visit request on its own (no clock needed), or None."""
    if not request.traveller_name.strip():
        return "traveller_name is blank: give the traveller's name"
    if len(request.traveller_name) > NAME_MOST_CHARS:
        return f"traveller_name is longer than {NAME_MOST_CHARS} characters"
    if request.tda_airport is request.home_airport:
        return f"tda_airport and home_airport are both {request.tda_airport.value}: give two different airports"
    dates = [("assignment_start", request.assignment_start), ("assignment_end", request.assignment_end),
             ("outbound_date", request.outbound_date), ("return_date", request.return_date)]
    if request.last_home_visit:
        dates.append(("last_home_visit", request.last_home_visit))
    for name, value in dates:
        if not is_date(value):
            return f"{name} {value!r} is not a real YYYY-MM-DD date (last_home_visit may be empty)"
    if days_between(request.assignment_start, request.assignment_end) < 0:
        return f"assignment_end {request.assignment_end} is before assignment_start {request.assignment_start}"
    stay = days_between(request.outbound_date, request.return_date)
    if stay < 0:
        return f"return_date {request.return_date} is before outbound_date {request.outbound_date}"
    if stay > LONGEST_VISIT_DAYS:
        return f"return_date is {stay} days after outbound_date: a visit lasts at most {LONGEST_VISIT_DAYS} days"
    if request.last_home_visit:
        if days_between(request.assignment_start, request.last_home_visit) < 0:
            return (f"last_home_visit {request.last_home_visit} is before the assignment starts "
                    f"({request.assignment_start}): give the last visit during this assignment, or leave it empty")
        if days_between(request.last_home_visit, request.outbound_date) <= 0:
            return f"last_home_visit {request.last_home_visit} is not before outbound_date {request.outbound_date}"
    return None


def booking_date_problem(outbound_date, return_date, booking_date):
    """What is wrong with flight days booked on ``booking_date`` (today), or None."""
    if days_between(booking_date, outbound_date) < 0:
        return f"outbound_date {outbound_date} is before today, {booking_date}: flights cannot leave in the past"
    if days_between(booking_date, return_date) > BOOKING_HORIZON_DAYS:
        return (f"return_date {return_date} is more than {BOOKING_HORIZON_DAYS} days after today, {booking_date}: "
                "flights are not sold that far ahead")
    return None


def assignment_days(start, end):
    """An assignment's length in days, its first and last day included."""
    return days_between(start, end) + 1


def previous_visit(request):
    """The day the frequency rule counts from: the last home visit, or the assignment start when none."""
    return request.last_home_visit or request.assignment_start


def request_plain(request):
    """A visit request as plain JSON values, the form receipts record and the verifier compares."""
    return {
        "traveller_name": request.traveller_name,
        "tda_airport": request.tda_airport.value,
        "home_airport": request.home_airport.value,
        "assignment_start": request.assignment_start,
        "assignment_end": request.assignment_end,
        "family_status": request.family_status.value,
        "duplicate_housing_obligation": request.duplicate_housing_obligation,
        "last_home_visit": request.last_home_visit,
        "manager_approved": request.manager_approved,
        "outbound_date": request.outbound_date,
        "return_date": request.return_date,
    }


def trip_refusal(trip):
    """C1-C8, in order: the first rule the visit itself breaks, or NONE. Every fact is on the trip."""
    if not TDA_MIN_DAYS <= trip.assignment_days <= TDA_MAX_DAYS:
        return Refusal.NOT_A_TDA
    if not trip.duplicate_housing_obligation:
        return Refusal.NO_DUPLICATE_HOUSING
    if trip.family_status is FamilyStatus.ACCOMPANIED:
        return Refusal.ACCOMPANIED
    if not trip.manager_approved:
        return Refusal.NO_MANAGER_APPROVAL
    if trip.estimated_driving_miles < AIRFARE_MILES:
        return Refusal.UNDER_400_MILES
    if (days_between(trip.assignment_start, trip.outbound_date) < 0
            or days_between(trip.return_date, trip.assignment_end) < 0):
        return Refusal.OUTSIDE_ASSIGNMENT
    if trip.days_since_previous_visit < VISIT_GAP_DAYS[trip.family_status]:
        return Refusal.TOO_SOON
    if trip.days_before_departure < ADVANCE_DAYS:
        return Refusal.UNDER_14_DAYS_ADVANCE
    return Refusal.NONE


def flies_trip(trip, offer):
    """Whether an offer flies the visit: from the assignment home on outbound_date, and back on return_date,
    each the local departure date at the airport the leg leaves from."""
    out, back = offer.outbound, offer.inbound
    return (
        bool(out) and bool(back)
        and out[0].origin == trip.tda.code and out[-1].destination == trip.home.code
        and back[0].origin == trip.home.code and back[-1].destination == trip.tda.code
        and out[0].depart_local[:10] == trip.outbound_date and back[0].depart_local[:10] == trip.return_date
    )


def fare_compliant(offer):
    """C9: a round-trip ticket, economy class, non-refundable."""
    return offer.ticket is TicketType.ROUND_TRIP and offer.cabin is Cabin.ECONOMY and not offer.refundable


@dataclass
class Answer:
    """The refusal or booking the rules require for a trip and its offers."""

    refusal: Refusal
    compliant: list  # offer ids allowed by C9
    lowest_fare_cents: int
    correct: list  # offer ids that are correct bookings


def solve(trip, offers):
    """C1-C8 on the visit, then C9 (round trip, economy, non-refundable) and C10 (the cheapest)."""
    refusal = trip_refusal(trip)
    if refusal is not Refusal.NONE:
        return Answer(refusal, [], 0, [])
    compliant = [offer for offer in offers if flies_trip(trip, offer) and fare_compliant(offer)]
    if not compliant:
        return Answer(Refusal.NO_COMPLIANT_FLIGHT, [], 0, [])
    lowest = min(offer.fare_cents for offer in compliant)
    return Answer(
        Refusal.NONE,
        [offer.offer_id for offer in compliant],
        lowest,
        [offer.offer_id for offer in compliant if offer.fare_cents == lowest],
    )


def segments_plain(segments):
    return [
        {
            "origin": segment.origin,
            "destination": segment.destination,
            "flight_number": segment.flight_number,
            "depart": segment.depart,
            "arrive": segment.arrive,
            "depart_local": segment.depart_local,
            "air_minutes": segment.air_minutes,
        }
        for segment in segments
    ]


def offer_plain(offer):
    """An offer as plain JSON values, the form both sides hash."""
    return {
        "offer_id": offer.offer_id,
        "carrier": offer.carrier,
        "ticket": offer.ticket.value,
        "cabin": offer.cabin.value,
        "refundable": offer.refundable,
        "fare_cents": offer.fare_cents,
        "outbound": segments_plain(offer.outbound),
        "inbound": segments_plain(offer.inbound),
    }


def offers_digest(offers):
    """The SHA-256 of a list of offers in their canonical JSON form."""
    text = json.dumps([offer_plain(offer) for offer in offers], sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def same_offers(left, right):
    """Whether two lists of offers are the same offers, in the same order."""
    return [offer_plain(offer) for offer in left] == [offer_plain(offer) for offer in right]

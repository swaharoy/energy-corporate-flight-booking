"""The simulated flight world, shared byte for byte by the tools (src/plugin/world.py) and the verifier
(verifier/world.py): real U.S. airports and real airline names, with synthetic schedules and fares; the
estimated driving distance between two airports; and the trip a visit request makes.

A flight's day is the local date at the airport it leaves from, and it leaves at 06:00-21:55 local time
there; times on segments are UTC, with the local departure time beside them. The one-way flights on a route
and day come from a SHA-256 stream keyed by the route and the day only, and the round-trip fares by the
route and both days, so the same search gives the same offers on every machine, on any booking date, and
the verifier can rebuild any search the agent made. Nothing here is real fare or
schedule data: airline names are used for realism only. It imports only modules a verifier may use,
contract, and the shared rules.
"""

import dataclasses
import hashlib
import math
from functools import cache

from contract import Airport, Cabin, Offer, Segment, TicketType, Trip

from .rules import (
    LONGEST_VISIT_DAYS,
    assignment_days,
    booking_date_problem,
    date_of,
    day_number,
    days_between,
    previous_visit,
    request_problem,
)

NOTE = "Simulated fares and schedules; airline names are used for realism only."

# Airports: OurAirports (https://ourairports.com/data/, public domain), fetched 2026-11-02: the 31 large U.S.
# airports of the trimmed list. The last column is the airport's standard-time UTC offset in minutes (no
# daylight saving), used for the local date and time of each departure.
# (code, name, city, latitude, longitude, UTC offset in minutes)
AIRPORTS = (
    ('ATL', 'Hartsfield Jackson Atlanta International Airport', 'Atlanta', 33.6367, -84.4281, -300),
    ('LAX', 'Los Angeles International Airport', 'Los Angeles', 33.9425, -118.408, -480),
    ('ORD', "Chicago O'Hare International Airport", 'Chicago', 41.9786, -87.9048, -360),
    ('DFW', 'Dallas Fort Worth International Airport', 'Dallas-Fort Worth', 32.8968, -97.038, -360),
    ('DEN', 'Denver International Airport', 'Denver', 39.86, -104.6738, -420),
    ('JFK', 'John F. Kennedy International Airport', 'New York', 40.6394, -73.7793, -300),
    ('SFO', 'San Francisco International Airport', 'San Francisco', 37.6198, -122.3748, -480),
    ('SEA', 'Seattle–Tacoma International Airport', 'Seattle', 47.4479, -122.3103, -480),
    ('LAS', 'Harry Reid International Airport', 'Las Vegas', 36.0834, -115.1518, -480),
    ('MCO', 'Orlando International Airport', 'Orlando', 28.4294, -81.309, -300),
    ('EWR', 'Newark Liberty International Airport', 'Newark', 40.6894, -74.1705, -300),
    ('MIA', 'Miami International Airport', 'Miami', 25.796, -80.2898, -300),
    ('CLT', 'Charlotte Douglas International Airport', 'Charlotte', 35.214, -80.9431, -300),
    ('PHX', 'Phoenix Sky Harbor International Airport', 'Phoenix', 33.4353, -112.0059, -420),
    ('IAH', 'George Bush Intercontinental Airport', 'Houston', 29.9844, -95.3414, -360),
    ('BOS', 'Boston Logan International Airport', 'Boston', 42.362, -71.0079, -300),
    ('MSP', 'Minneapolis–Saint Paul International Airport / Wold–Chamberlain Field', 'Minneapolis', 44.8801, -93.2217, -360),
    ('DTW', 'Detroit Metropolitan Wayne County Airport', 'Detroit', 42.2138, -83.3538, -300),
    ('PHL', 'Philadelphia International Airport', 'Philadelphia', 39.8719, -75.2411, -300),
    ('LGA', 'LaGuardia Airport', 'New York', 40.7772, -73.8726, -300),
    ('BWI', 'Baltimore/Washington International Thurgood Marshall Airport', 'Baltimore', 39.1754, -76.6683, -300),
    ('SLC', 'Salt Lake City International Airport', 'Salt Lake City', 40.7889, -111.9799, -420),
    ('SAN', 'San Diego International Airport', 'San Diego', 32.7336, -117.19, -480),
    ('IAD', 'Washington Dulles International Airport', 'Dulles', 38.9445, -77.4558, -300),
    ('DCA', 'Ronald Reagan Washington National Airport', 'Washington', 38.8521, -77.0377, -300),
    ('TPA', 'Tampa International Airport', 'Tampa', 27.9755, -82.5332, -300),
    ('AUS', 'Austin Bergstrom International Airport', 'Austin', 30.1975, -97.662, -360),
    ('BNA', 'Nashville International Airport', 'Nashville', 36.1245, -86.6782, -360),
    ('HNL', 'Daniel K. Inouye International Airport', 'Honolulu, Oahu', 21.3184, -157.9257, -600),
    ('ANC', 'Ted Stevens Anchorage International Airport', 'Anchorage', 61.179, -149.9926, -540),
    ('STL', 'St. Louis Lambert International Airport', 'St Louis', 38.7487, -90.37, -360),
)

# U.S. airlines: (IATA code, name, kind, longest nonstop in km, hubs and focus airports among AIRPORTS, premium
# cabin sold and the shortest nonstop in km it is sold on, or None). kind: "network" or "low" (low-cost).
AIRLINES = (
    ("DL", "Delta Air Lines", "network", 8000, ("ATL", "DTW", "MSP", "SLC", "JFK", "LAX", "SEA", "BOS", "LGA"),
     ("FIRST", 0)),
    ("UA", "United Airlines", "network", 8000, ("ORD", "DEN", "IAH", "EWR", "SFO", "IAD", "LAX"), ("FIRST", 0)),
    ("AA", "American Airlines", "network", 8000, ("DFW", "CLT", "ORD", "MIA", "PHL", "PHX", "JFK", "LAX", "DCA",
                                                   "LGA"), ("FIRST", 0)),
    ("AS", "Alaska Airlines", "low", 8000, ("SEA", "ANC", "SFO", "LAX", "SAN", "HNL"), ("FIRST", 0)),
    ("B6", "JetBlue", "low", 5800, ("JFK", "BOS", "MCO"), ("BUSINESS", 3_500)),
    ("WN", "Southwest Airlines", "low", 4400, ("LAS", "DEN", "BWI", "PHX", "AUS", "BNA", "STL", "MCO", "TPA"),
     None),
)

# The driving-distance estimate (the policy measures "the most direct ground travel route"): great-circle
# miles x 1.2, a common U.S. road circuity factor (Ballou, Rahardja & Sakai 2002).
ROAD_CIRCUITY = 1.2
KM_PER_MILE = 1.609344
EARTH_RADIUS_KM = 6371.0

# Synthetic schedule and fare model. Every constant is a modelling choice, not real data.
CRUISE_KMH = 870  # block speed: minutes in the air = TAXI_MINUTES + distance at this speed
TAXI_MINUTES = 20
FIRST_DEPARTURE = 6 * 60  # first departures leave at 06:00 local time, the last at 21:55
LAST_DEPARTURE = 22 * 60
MIN_CONNECTION, MAX_CONNECTION = 45, 240  # minutes between flights at the hub
MOST_ITINERARIES = 3  # itineraries flown on a route a day (nonstops and connections)
MOST_NONSTOPS = 2
DETOUR = 1.35  # a connection flies at most this times the direct distance
SHORTEST_LEG_KM = 250
TWO_ONE_WAYS_PERCENT = 45  # the share of searches where two one-way tickets are sold too


def fare_base(km):
    """A one-way economy fare in cents for a nonstop of ``km``: $50 plus a concave per-distance part."""
    return 5_000 + round(30 * km ** 0.85)


class Rng:
    """A pseudo-random stream built on SHA-256: the same numbers on every machine and Python version."""

    def __init__(self, label):
        self.prefix = f"energy-corporate-flight-booking:{label}:"
        self.count = 0

    def bits(self):
        digest = hashlib.sha256(f"{self.prefix}{self.count}".encode()).digest()
        self.count += 1
        return int.from_bytes(digest[:8], "big")

    def randint(self, low, high):
        """An integer from low to high, both included."""
        if high < low:
            raise ValueError(f"empty range {low}..{high}")
        return low + self.bits() % (high - low + 1)

    def choice(self, items):
        if not items:
            raise ValueError("choice from an empty sequence")
        return items[self.randint(0, len(items) - 1)]

    def chance(self, percent):
        return self.randint(1, 100) <= percent

    def shuffled(self, items):
        items = list(items)
        for index in range(len(items) - 1, 0, -1):
            other = self.randint(0, index)
            items[index], items[other] = items[other], items[index]
        return items


@cache
def airport_table():
    """{code: (code, name, city, latitude, longitude, UTC offset)}"""
    return {row[0]: row for row in AIRPORTS}


@cache
def airline_table():
    return {row[0]: row for row in AIRLINES}


def is_airport(code):
    return code in airport_table()


def airport(code):
    row = airport_table().get(code)
    if row is None:
        raise ValueError(f"unknown airport {code!r}")
    return Airport(code=row[0], name=row[1], city=row[2])


@cache
def great_circle_km(origin, destination):
    """Great-circle distance between two airports, in km (unrounded)."""
    a, b = airport_table()[origin], airport_table()[destination]
    lat1, lon1, lat2, lon2 = (math.radians(value) for value in (a[3], a[4], b[3], b[4]))
    h = math.sin((lat2 - lat1) / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2
    return 2 * EARTH_RADIUS_KM * math.asin(math.sqrt(h))


def distance_km(origin, destination):
    return round(great_circle_km(origin, destination))


def driving_miles(origin, destination):
    """The estimated driving distance in whole miles: great-circle miles x ROAD_CIRCUITY."""
    return round(great_circle_km(origin, destination) / KM_PER_MILE * ROAD_CIRCUITY)


def air_minutes(origin, destination):
    """Minutes in the air for a nonstop flight: distance at block speed, plus taxi time."""
    return TAXI_MINUTES + round(distance_km(origin, destination) * 60 / CRUISE_KMH)


def leg_allowed(airline, origin, destination):
    km = distance_km(origin, destination)
    return SHORTEST_LEG_KM <= km <= airline[3]


@cache
def itineraries(origin, destination):
    """Every (airline code, airports flown through) an airline plausibly sells on a route: a nonstop when one
    end is its hub, and connections through its own hubs that add little distance."""
    direct = distance_km(origin, destination)
    found = []
    for airline in AIRLINES:
        code, hubs = airline[0], airline[4]
        if (origin in hubs or destination in hubs) and leg_allowed(airline, origin, destination):
            found.append((code, (origin, destination)))
        if direct < 600:
            continue
        via = [
            hub for hub in hubs
            if is_airport(hub) and hub not in (origin, destination)
            and leg_allowed(airline, origin, hub) and leg_allowed(airline, hub, destination)
            and distance_km(origin, hub) + distance_km(hub, destination) <= DETOUR * direct
        ]
        via.sort(key=lambda hub: (distance_km(origin, hub) + distance_km(hub, destination), hub))
        found.extend((code, (origin, hub, destination)) for hub in via[:2])
    return tuple(found)


def time_text(minute):
    """YYYY-MM-DD HH:MM of a minute number (minutes since 1970-01-01 00:00 UTC)."""
    return f"{date_of(minute // 1440)} {minute % 1440 // 60:02d}:{minute % 60:02d}"


def utc_offset(code):
    """An airport's standard-time UTC offset in minutes (local = UTC + offset)."""
    return airport_table()[code][5]


def local_text(minute, code):
    """YYYY-MM-DD HH:MM local time at airport ``code`` of a UTC minute number."""
    return time_text(minute + utc_offset(code))


def departure_minute(rng, code, day):
    """The UTC minute of a departure from airport ``code`` at 06:00-21:55 local time, in 5-minute steps, on
    day number ``day``: the local date at that airport."""
    local = rng.randint(FIRST_DEPARTURE // 5, (LAST_DEPARTURE - 5) // 5) * 5
    return day * 1440 + local - utc_offset(code)


def flight_number(code, origin, destination):
    """A stable flight number for an airline's leg, e.g. "UA 1482"."""
    digest = hashlib.sha256(f"flight:{code}:{origin}:{destination}".encode()).digest()
    return f"{code} {1 + int.from_bytes(digest[:4], 'big') % 2999}"


def build_segments(rng, airline_code, path, day):
    start = departure_minute(Rng(f"time:{airline_code}:{'-'.join(path)}:{day}"), path[0], day)
    segments = []
    for index in range(len(path) - 1):
        a, b = path[index], path[index + 1]
        air = air_minutes(a, b)
        segments.append(Segment(origin=a, destination=b, flight_number=flight_number(airline_code, a, b),
                                depart=time_text(start), arrive=time_text(start + air),
                                depart_local=local_text(start, a), air_minutes=air))
        start += air + rng.randint(MIN_CONNECTION // 5, MAX_CONNECTION // 5) * 5
    return segments


@cache
def route_itineraries(origin, destination):
    """The itineraries that fly a route, the same every day and in both directions (an airline flying a route
    flies it back): up to MOST_NONSTOPS nonstops and connections up to MOST_ITINERARIES in all."""
    a, b = sorted((origin, destination))
    rng = Rng(f"route:{a}:{b}")
    options = itineraries(a, b)
    nonstops = [option for option in options if len(option[1]) == 2]
    connections = [option for option in options if len(option[1]) == 3]
    chosen = rng.shuffled(nonstops)[:MOST_NONSTOPS]
    chosen += rng.shuffled(connections)[: MOST_ITINERARIES - len(chosen)]
    if (a, b) == (origin, destination):
        return tuple(chosen)
    return tuple((code, tuple(reversed(path))) for code, path in chosen)


@cache
def day_flights(origin, destination, day):
    """The one-way itineraries flown on a route on day number ``day`` (the local date at ``origin``): (airline
    code, segments, one-way economy fare), sorted by departure. The same whatever the return day."""
    rng = Rng(f"day:{origin}:{destination}:{day}")
    direct = distance_km(origin, destination)
    flights = []
    for airline_code, path in route_itineraries(origin, destination):
        if not rng.chance(95):  # an itinerary that does not operate that day
            continue
        airline = airline_table()[airline_code]
        fare = fare_base(direct) * rng.randint(80, 135) // 100
        if len(path) == 3:
            fare = fare * rng.randint(78, 95) // 100
        if airline[2] == "low":
            fare = fare * 88 // 100
        segments = build_segments(Rng(f"segments:{origin}:{destination}:{day}:{airline_code}:{'-'.join(path)}"),
                                  airline_code, path, day)
        flights.append((airline_code, tuple(segments), fare))
    flights.sort(key=lambda flight: (flight[1][0].depart, flight[2], flight[0]))
    return tuple(flights)


def premium_cabin(airline, km):
    """The premium cabin an airline sells on a route of ``km``, or None."""
    premium = airline[5]
    if premium is None or km < premium[1]:
        return None
    return Cabin(premium[0])


def trip_drafts(origin, destination, out_day, back_day):
    """The offers before numbering: (first departure, fare, sort tag, carrier, ticket, cabin, refundable,
    outbound segments, inbound segments)."""
    rng = Rng(f"trip:{origin}:{destination}:{out_day}:{back_day}")
    out = day_flights(origin, destination, out_day)
    back = day_flights(destination, origin, back_day)
    km = distance_km(origin, destination)
    drafts = []
    for code in sorted({flight[0] for flight in out} & {flight[0] for flight in back}):
        airline = airline_table()[code]
        there = next(flight for flight in out if flight[0] == code)
        home = next(flight for flight in back if flight[0] == code)
        legs = (list(there[1]), list(home[1]))
        economy = (there[2] + home[2]) * rng.randint(90, 102) // 100
        drafts.append((economy, Cabin.ECONOMY, False, legs, airline[1], TicketType.ROUND_TRIP))
        if rng.chance(85):  # a flexible, refundable economy fare
            drafts.append((economy * rng.randint(125, 210) // 100, Cabin.ECONOMY, True, legs, airline[1],
                           TicketType.ROUND_TRIP))
        cabin = premium_cabin(airline, km)
        if cabin is not None and rng.chance(80):
            premium = economy * rng.randint(170, 320) // 100
            if rng.chance(15):  # an upgrade sale, close to economy
                premium = economy * rng.randint(108, 135) // 100
            drafts.append((premium, cabin, rng.chance(40), legs, airline[1], TicketType.ROUND_TRIP))
    if out and back and rng.chance(TWO_ONE_WAYS_PERCENT):
        there = min(out, key=lambda flight: (flight[2], flight[1][0].depart))
        home = min(back, key=lambda flight: (flight[2], flight[1][0].depart))
        names = [airline_table()[there[0]][1], airline_table()[home[0]][1]]
        carrier = names[0] if names[0] == names[1] else f"{names[0]} / {names[1]}"
        fare = (there[2] + home[2]) * rng.randint(82, 108) // 100
        drafts.append((fare, Cabin.ECONOMY, False, (list(there[1]), list(home[1])), carrier,
                       TicketType.TWO_ONE_WAYS))
    return [
        (legs[0][0].depart, fare, f"{cabin.value}:{ticket.value}:{refundable}", carrier, ticket, cabin, refundable,
         legs[0], legs[1])
        for fare, cabin, refundable, legs, carrier, ticket in drafts
    ]


@cache
def built_trip(origin, destination, out_day, back_day):
    if not is_airport(origin) or not is_airport(destination):
        raise ValueError(f"unknown route {origin!r} -> {destination!r}")
    if origin == destination:
        raise ValueError("origin and destination are the same airport")
    if not 0 <= back_day - out_day <= LONGEST_VISIT_DAYS:
        raise ValueError(f"the return day must be 0 to {LONGEST_VISIT_DAYS} days after the outbound day")
    drafts = sorted(trip_drafts(origin, destination, out_day, back_day), key=lambda d: (d[0], d[1], d[2], d[3]))
    stamp = f"{date_of(out_day).replace('-', '')}-{date_of(back_day).replace('-', '')}"
    return tuple(
        Offer(
            offer_id=f"{stamp}-{index:02d}",
            carrier=carrier,
            ticket=ticket,
            cabin=cabin,
            refundable=refundable,
            fare_cents=fare,
            outbound=list(outbound),
            inbound=list(inbound),
        )
        for index, (_, fare, _, carrier, ticket, cabin, refundable, outbound, inbound) in enumerate(drafts, start=1)
    )


def trip_offers(origin, destination, out_day, back_day):
    """Every offer out from ``origin`` on day number ``out_day`` (the local date at ``origin``) and back on
    ``back_day`` (the local date at ``destination``), in departure order, numbered <out date>-<back date>-01, ... Fresh copies on each call, so no caller can change another's."""
    return tuple(
        dataclasses.replace(
            offer,
            outbound=[dataclasses.replace(segment) for segment in offer.outbound],
            inbound=[dataclasses.replace(segment) for segment in offer.inbound],
        )
        for offer in built_trip(origin, destination, out_day, back_day)
    )


def offers_for(origin, destination, outbound_date, return_date):
    """Every offer leaving ``origin`` on outbound_date and ``destination`` on return_date (local dates at each,
    0 to LONGEST_VISIT_DAYS days apart)."""
    return list(trip_offers(origin, destination, day_number(outbound_date), day_number(return_date)))


def make_trip(request, booking_date):
    """The trip a visit request makes, booked on ``booking_date``; raises when it cannot be booked that day."""
    problem = request_problem(request) or booking_date_problem(request.outbound_date, request.return_date,
                                                               booking_date)
    if problem:
        raise ValueError(problem)
    tda, home = request.tda_airport.value, request.home_airport.value
    return Trip(
        traveller_name=request.traveller_name,
        tda=airport(tda),
        home=airport(home),
        assignment_start=request.assignment_start,
        assignment_end=request.assignment_end,
        assignment_days=assignment_days(request.assignment_start, request.assignment_end),
        family_status=request.family_status,
        duplicate_housing_obligation=request.duplicate_housing_obligation,
        manager_approved=request.manager_approved,
        last_home_visit=request.last_home_visit,
        days_since_previous_visit=days_between(previous_visit(request), request.outbound_date),
        outbound_date=request.outbound_date,
        return_date=request.return_date,
        booking_date=booking_date,
        days_before_departure=days_between(booking_date, request.outbound_date),
        estimated_driving_miles=driving_miles(tda, home),
    )

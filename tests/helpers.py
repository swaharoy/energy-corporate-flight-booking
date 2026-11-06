"""Building values the way NanoAgent's sandbox does, and running the tools and verifier like the host."""

from __future__ import annotations

import hashlib
from contextlib import contextmanager
from pathlib import Path

from slimconfig import build_output, plain_output

import verifier
import verifier.world
from contract import TASKS, TOOLS, AirportCode, Offer, SearchInput, SolveOutput, Task, Tool, TripInput
from plugin import get_trip, search_flights, solve_booking, world
from plugin.rules import date_of, day_number

BOOK = Task.BOOK_FLIGHT.value
CODES = [member.value for member in AirportCode]
TODAY = "2026-11-05"


def plain_request(**changes) -> dict:
    """A visit request as plain JSON: by default a single traveller on a Houston assignment going home to
    Denver, out 2026-12-04 and back 2026-12-07, that passes rules C1-C8."""
    return {
        "traveller_name": "Jordan Lee", "tda_airport": "IAH", "home_airport": "DEN",
        "assignment_start": "2026-09-01", "assignment_end": "2027-02-28", "family_status": "SINGLE",
        "duplicate_housing_obligation": True, "last_home_visit": "2026-11-02", "manager_approved": True,
        "outbound_date": "2026-12-04", "return_date": "2026-12-07",
    } | changes


def request(**changes) -> TripInput:
    return build_output(plain_request(**changes), TripInput)


def requests(count: int, salt: str = "requests"):
    """``count`` varied visit requests, chosen by SHA-256 so they are the same on every machine: any route,
    assignments of 60 to 400 days, every status, housing and approval, visits 5 to 60 days ahead. Most pass
    C1-C8; each rule refuses some."""
    for index in range(count):
        digest = hashlib.sha256(f"{salt}:{index}".encode()).digest()
        tda = CODES[digest[0] % len(CODES)]
        home = CODES[digest[1] % len(CODES)]
        if tda == home:
            continue
        today = day_number(TODAY)
        outbound = today + 5 + digest[2] % 56
        stay = digest[3] % 8
        start = outbound - 20 - digest[4] % 120
        length = (60, 91, 120, 180, 250, 300, 365, 366, 400, 200)[digest[5] % 10]
        if digest[6] % 9 == 0:
            length = outbound - start  # the visit's return falls after the assignment
        status = ("SINGLE", "UNACCOMPANIED", "SINGLE", "UNACCOMPANIED", "ACCOMPANIED", "SINGLE")[digest[7] % 6]
        gap = digest[8] % 50
        last = date_of(outbound - gap) if gap and outbound - gap > start else ""
        yield request(tda_airport=tda, home_airport=home, assignment_start=date_of(start),
                      assignment_end=date_of(start + length - 1), family_status=status,
                      duplicate_housing_obligation=digest[9] % 10 != 0, last_home_visit=last,
                      manager_approved=digest[10] % 10 != 0, outbound_date=date_of(outbound),
                      return_date=date_of(outbound + stay))


def booking(run_id: str, offer_id: str = "", *, booked: bool = True, refusal: str = "NONE") -> dict:
    return {"run_id": run_id, "booked": booked, "refusal": refusal, "offer_id": offer_id}


def judge(arguments: TripInput, output: dict, reference: SolveOutput | None, workspace: Path) -> dict:
    """verify_task on plain values built into their contract classes, as the sandbox does."""
    given, made = TASKS[Task.BOOK_FLIGHT]
    key = None if reference is None else build_output(plain_output(reference), SolveOutput)
    return verifier.verify_task(BOOK, build_output(plain_output(arguments), given), build_output(output, made), key,
                                str(workspace))


class Run:
    """One booking run: the answer key pinned in a scratch folder, then get_trip and a search in the workspace."""

    def __init__(self, value: TripInput, root: Path, *, search: bool = True) -> None:
        self.request = value
        self.workspace = root / "workspace"
        self.workspace.mkdir(parents=True, exist_ok=True)
        scratch = root / "scratch"
        scratch.mkdir(parents=True, exist_ok=True)
        self.key = solve_booking(value, scratch)
        started = get_trip(value, self.workspace)
        self.run_id = started.run_id
        self.trip = started.trip
        self.offers = []
        if search:
            self.offers = self.search().offers

    def search(self, outbound_date: str | None = None, return_date: str | None = None, *, origin=None,
               destination=None):
        trip = self.trip
        return search_flights(
            SearchInput(self.run_id, AirportCode(origin or trip.tda.code), AirportCode(destination or trip.home.code),
                        outbound_date or trip.outbound_date, return_date or trip.return_date),
            self.workspace,
        )

    def gold(self) -> dict:
        key = self.key
        if key.refusal.value != "NONE":
            return booking(self.run_id, booked=False, refusal=key.refusal.value)
        return booking(self.run_id, key.correct_offer_ids[0])

    def judge(self, output: dict) -> dict:
        return judge(self.request, output, self.key, self.workspace)


def failed(verdict: dict) -> list[str]:
    return [entry["id"] for entry in verdict["details"]["checks"] if entry["ok"] is False]


def tool_input(tool: str, value: dict) -> dict:
    return verifier.verify_input(tool, build_output(value, TOOLS[Tool(tool)][0]))


@contextmanager
def hand_built(offers: list[dict] | None = None, route: tuple = ("IAH", "DEN"), miles: int | None = None):
    """The world replaced, in the tools and the verifier alike: ``offers`` (plain, hand-built) are the only
    offers on ``route`` for the days their flights leave (local dates at each leg's origin), and no other route
    or days have any; ``miles``, when
    given, is the estimated driving distance between any two airports. Used for exact boundaries."""
    saved = world.trip_offers, verifier.world.trip_offers, world.driving_miles, verifier.world.driving_miles
    if offers is not None:
        built = tuple(build_output(offer, Offer) for offer in offers)

        def trip_offers(origin, destination, out_day, back_day):
            return tuple(
                offer for offer in built
                if (origin, destination) == route
                and day_number(offer.outbound[0].depart_local[:10]) == out_day
                and day_number(offer.inbound[0].depart_local[:10]) == back_day
            )

        world.trip_offers = verifier.world.trip_offers = trip_offers
    if miles is not None:
        world.driving_miles = verifier.world.driving_miles = lambda origin, destination: miles
    try:
        yield
    finally:
        world.trip_offers, verifier.world.trip_offers, world.driving_miles, verifier.world.driving_miles = saved


def offer(offer_id: str, fare: int, *, ticket: str = "ROUND_TRIP", cabin: str = "ECONOMY", refundable: bool = False,
          out: str = "2026-12-04 15:00", back: str = "2026-12-07 15:00", route: tuple = ("IAH", "DEN"),
          carrier: str = "United Airlines") -> dict:
    """A plain hand-built round-trip offer: a nonstop each way, leaving at ``out`` and ``back``, local times at
    each leg's origin."""
    origin, destination = route

    def segment(a, b, depart, number):
        local = day_number(depart[:10]) * 1440 + int(depart[11:13]) * 60 + int(depart[14:16])
        start = local - world.utc_offset(a)
        return {"origin": a, "destination": b, "flight_number": f"UA {number}", "depart": world.time_text(start),
                "arrive": world.time_text(start + 150), "depart_local": world.local_text(start, a),
                "air_minutes": 150}

    return {"offer_id": offer_id, "carrier": carrier, "ticket": ticket, "cabin": cabin, "refundable": refundable,
            "fare_cents": fare, "outbound": [segment(origin, destination, out, 100)],
            "inbound": [segment(destination, origin, back, 101)]}

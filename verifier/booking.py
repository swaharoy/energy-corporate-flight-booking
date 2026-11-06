"""The energy-corporate-flight-booking verdict: named checks, in order, on the answer key, the run the
submission names, its search receipts, and the refusal or booking against rules C1-C10.

Every search receipt is checked against the simulated world rebuilt here (verifier/world.py, the tools' own
file), so any offer the agent saw, on any days it searched, is known exactly.

The first five checks are integrity gates; the rest are the policy. The verdict is valid, scoring 1, only
when every check holds; any failure, gate or policy, scores 0: a booking follows the policy or it does not.
A check that depends on a failed one is "not checked". Expected values come from the verifier's own copy of
the rules applied to the pinned trip and offers; the answer key's own answer is checked to agree with them.
"""

from contract import Cabin, Refusal, TicketType

from .checks import check, result, run_files
from .rules import (
    ADVANCE_DAYS,
    AIRFARE_MILES,
    TDA_MAX_DAYS,
    TDA_MIN_DAYS,
    VISIT_GAP_DAYS,
    flies_trip,
    offers_digest,
    request_plain,
    solve,
)
from .solve import answer_key_problem
from .world import offers_for

TEXT = {
    "answer-key": "The answer key pinned this request's visit, booked today, its offers, and an answer that follows the rules",
    "this-run": "The submission names a run get_trip began for this request on the same booking date, after the answer key",
    "searched": "The agent searched for flights in this run before booking or finding none compliant",
    "receipts-match": "Every search in this run returned exactly the route's offers for its query",
    "offer-seen": "The booked offer was among this run's search results, from the assignment home and back",
    "refusal": "C1-C9: book unless a rule refuses the visit, and then give the first rule's reason",
    "dates": "The booked offer leaves for home on outbound_date and back on return_date, local dates where each leg leaves",
    "ticket": "C9: one round-trip ticket, not two one-way tickets",
    "cabin": "C9: economy class",
    "refundable": "C9: a non-refundable fare",
    "fare": "C10: the lowest compliant fare",
}
GATES = ("answer-key", "this-run", "searched", "receipts-match", "offer-seen")
POLICY = ("refusal", "dates", "ticket", "cabin", "refundable", "fare")


def money(cents):
    return f"${cents // 100}.{cents % 100:02d}"


class Verdict:
    def __init__(self):
        self.entries = {}
        self.blocked_by = None

    def add(self, check_id, ok, expected="", actual="", message=""):
        if self.blocked_by is not None:
            self.entries[check_id] = check(
                check_id, TEXT[check_id], None, message=f"not checked: {self.blocked_by} failed"
            )
            return
        self.entries[check_id] = check(check_id, TEXT[check_id], ok, expected, actual, message)
        if not ok:
            self.blocked_by = check_id

    def finish(self):
        entries = [self.entries[check_id] for check_id in GATES + POLICY]
        failed = [entry for entry in entries if entry["ok"] is False]
        if not failed:
            return result(True, "valid: the answer follows every rule", score=1.0, checks=entries)
        first = failed[0]
        return result(False, f"{first['id']}: {first['message']}", score=0.0, checks=entries)


def verify_task(arguments, output, reference, workspace):
    verdict = Verdict()
    # Gate 1: the answer key.
    problem = "no answer key was pinned" if reference is None else answer_key_problem(arguments, reference)
    visit = (f"{arguments.tda_airport.value}-{arguments.home_airport.value}, out {arguments.outbound_date}, "
             f"back {arguments.return_date}")
    verdict.add("answer-key", problem is None, f"the key of {visit}", "none" if reference is None else
                f"booked {reference.trip.booking_date}", problem or "the answer key is this request's and follows the rules")
    if problem is not None:
        for check_id in GATES[1:] + POLICY:
            verdict.add(check_id, None)
        return verdict.finish()
    trip, offers = reference.trip, reference.offers
    answer = solve(trip, offers)

    # Gate 2: this run.
    started, searches = run_files(workspace, output.run_id)
    if not isinstance(started, dict) or started.get("request") != request_plain(arguments):
        verdict.add("this-run", False, "a run of this request", output.run_id,
                    f"the workspace holds no run {output.run_id!r} begun by get_trip for this request")
    elif started.get("booking_date") != trip.booking_date:
        verdict.add("this-run", False, f"booked {trip.booking_date}", str(started.get("booking_date")),
                    f"run {output.run_id} was booked on another day than the answer key")
    elif not isinstance(started.get("started_at"), str) or started["started_at"] < reference.pinned_at:
        verdict.add("this-run", False, f"begun after {reference.pinned_at}", str(started.get("started_at")),
                    f"run {output.run_id} began before this task's answer key: it is an earlier run")
    else:
        verdict.add("this-run", True, actual=output.run_id, message=f"run {output.run_id} began at {started['started_at']}")

    # Gate 3: searched before booking, or before finding no compliant fare (a refusal by C1-C8 needs no search).
    needs_search = output.booked or output.refusal is Refusal.NO_COMPLIANT_FLIGHT
    if needs_search and not searches:
        verdict.add("searched", False, "at least one search_flights call", "none",
                    "the agent booked, or found no compliant fare, without calling search_flights in this run")
    else:
        verdict.add("searched", True, actual=f"{len(searches)} searches", message="searched" if searches else
                    "a refusal by the visit's own facts needs no search")

    # Gate 4: every search receipt matches the simulated world's offers for its query.
    seen = {}
    mismatch = None
    for number, receipt in enumerate(searches, start=1):
        if not isinstance(receipt, dict):
            mismatch = f"search {number}'s receipt is unreadable"
            break
        try:
            expected = offers_for(receipt["origin"], receipt["destination"], receipt["outbound_date"],
                                  receipt["return_date"])
        except (KeyError, TypeError, ValueError):
            mismatch = f"search {number}'s receipt is malformed"
            break
        if receipt.get("offer_ids") != [o.offer_id for o in expected] or receipt.get("digest") != offers_digest(expected):
            mismatch = f"search {number} returned offers other than the route's offers for its query"
            break
        seen.update({o.offer_id: o for o in expected})
    verdict.add("receipts-match", mismatch is None, "receipts equal to the route's offers", mismatch or "equal",
                mismatch or f"{len(searches)} search receipts match the simulated offers")

    # Gate 5: the booked offer was seen, from the assignment home and back.
    route = f"{trip.tda.code}-{trip.home.code}-{trip.tda.code}"
    if output.booked and output.offer_id not in seen:
        verdict.add("offer-seen", False, "an offer id from this run's search results", output.offer_id,
                    f"offer {output.offer_id!r} was not among this run's search results")
    elif output.booked:
        flown = seen[output.offer_id]
        flies = f"{flown.outbound[0].origin}-{flown.outbound[-1].destination}-{flown.inbound[-1].destination}"
        verdict.add("offer-seen", flies == route, f"an offer {route}", f"{output.offer_id} flies {flies}",
                    f"offer {output.offer_id} was in the search results" if flies == route else
                    f"offer {output.offer_id} flies {flies}, not the visit's route {route}")
    else:
        verdict.add("offer-seen", True, message="nothing booked")

    # Policy: refusal or booking.
    want = answer.refusal
    shape_problem = None
    if output.booked and output.refusal is not Refusal.NONE:
        shape_problem = f"booked is true but refusal is {output.refusal.value}: a booking has refusal NONE"
    elif not output.booked and output.refusal is Refusal.NONE:
        shape_problem = "nothing is booked but refusal is NONE: give the reason"
    elif not output.booked and output.offer_id:
        shape_problem = "nothing is booked: offer_id must be empty"
    got = "booked" if output.booked else f"not booked ({output.refusal.value})"
    expected = "booked" if want is Refusal.NONE else f"not booked ({want.value})"
    if shape_problem:
        verdict.add("refusal", False, expected, got, shape_problem)
    else:
        verdict.add("refusal", got == expected, expected, got, refusal_reason(trip, want))
    if not output.booked or verdict.blocked_by is not None:
        message = "nothing is booked" if verdict.blocked_by is None else None
        for check_id in POLICY[1:]:
            if message:
                verdict.add(check_id, True, message=f"not applicable: {message}")
            else:
                verdict.add(check_id, None)
        return verdict.finish()

    offer = seen[output.offer_id]
    oid = offer.offer_id
    out_day, back_day = offer.outbound[0].depart_local[:10], offer.inbound[0].depart_local[:10]
    verdict.add("dates", flies_trip(trip, offer), f"out {trip.outbound_date}, back {trip.return_date}",
                f"out {out_day}, back {back_day}",
                f"offer {oid} leaves {trip.tda.code} on {out_day} and {trip.home.code} on {back_day} (local dates); "
                f"the visit is out {trip.outbound_date}, back {trip.return_date}")
    verdict.add("ticket", offer.ticket is TicketType.ROUND_TRIP, TicketType.ROUND_TRIP.value, offer.ticket.value,
                f"offer {oid} is {'one round-trip ticket' if offer.ticket is TicketType.ROUND_TRIP else 'two one-way tickets'};"
                " home-visit airfare is round trip only")
    verdict.add("cabin", offer.cabin is Cabin.ECONOMY, Cabin.ECONOMY.value, offer.cabin.value,
                f"offer {oid} is {offer.cabin.value.lower()} class; home-visit airfare is economy only")
    verdict.add("refundable", not offer.refundable, "non-refundable", "refundable" if offer.refundable else
                "non-refundable", f"offer {oid} is {'refundable' if offer.refundable else 'non-refundable'}; "
                "home-visit airfare is non-refundable only")
    verdict.add("fare", offer.fare_cents == answer.lowest_fare_cents, money(answer.lowest_fare_cents),
                money(offer.fare_cents), f"offer {oid} costs {money(offer.fare_cents)}; the lowest round-trip, economy, "
                f"non-refundable fare is {money(answer.lowest_fare_cents)}")
    return verdict.finish()


def refusal_reason(trip, want):
    """Why the rules give ``want`` for this visit, naming the fact that decides it."""
    if want is Refusal.NOT_A_TDA:
        return (f"the assignment lasts {trip.assignment_days} days: a temporary domestic assignment lasts "
                f"{TDA_MIN_DAYS}-{TDA_MAX_DAYS} days (shorter is a business trip)")
    if want is Refusal.NO_DUPLICATE_HOUSING:
        return "return home visits apply only with a duplicate housing obligation, and the traveller keeps no home"
    if want is Refusal.ACCOMPANIED:
        return "an accompanied traveller (family at the assignment) gets no return home visits"
    if want is Refusal.NO_MANAGER_APPROVAL:
        return "a return home visit needs the manager's approval, and it has none"
    if want is Refusal.UNDER_400_MILES:
        return (f"the locations are an estimated {trip.estimated_driving_miles} miles apart: airfare needs "
                f"{AIRFARE_MILES} or more, so the traveller drives")
    if want is Refusal.OUTSIDE_ASSIGNMENT:
        return (f"the visit (out {trip.outbound_date}, back {trip.return_date}) is not within the assignment, "
                f"{trip.assignment_start} to {trip.assignment_end}")
    if want is Refusal.TOO_SOON:
        return (f"the visit leaves {trip.days_since_previous_visit} days after the previous one: "
                f"{trip.family_status.value} allows one every {VISIT_GAP_DAYS[trip.family_status]} days")
    if want is Refusal.UNDER_14_DAYS_ADVANCE:
        return (f"the visit leaves {trip.days_before_departure} days after booking: home-visit airfare is a "
                f"{ADVANCE_DAYS}-day advance purchase")
    if want is Refusal.NO_COMPLIANT_FLIGHT:
        return "no round-trip, economy, non-refundable fare flies the visit's days"
    return "the visit passes every rule and a compliant fare exists: book the lowest"

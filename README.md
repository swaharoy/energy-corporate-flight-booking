# Energy Corporate Flight Booking

A NanoAgent plugin (`nanoagent.plugin/v0001`): an employee of an energy company on a temporary domestic
assignment describes, in plain words, a return home visit they want; an agent either refuses it with the
policy's exact reason or books the one round-trip flight the policy allows, as of today; and a
deterministic verifier checks the answer against every rule.

The policy is based on Chevron's public **U.S. Temporary Domestic Assignment Program, Up to 12 Months
(91-365 days)**, effective January 1, 2013, updated 2014
(<https://hr2.chevron.com/-/media/hr2/life-events/documents/USDomesticTemporaryAssignmentPolicy_UpTo12Months.pdf>):
its definitions (pp. 3-4, 9) and its return home visits (p. 15). This plugin is **unofficial**: it is not
made, endorsed or used by Chevron, and it restates the policy as exact rules of its own (below).

**Simulated fares and schedules.** Airports and airline names are real; every flight, fare and schedule is
synthetic, made by the plugin (see *The simulated flights* below). Airline names are used for realism
only: nothing here is a real fare or a real timetable.

## Tools

| Tool | Does | Code |
|---|---|---|
| `booking_requirements` | What a home-visit request must give, field by field with examples (read from the contract), the date rules, the airports to choose from, and an example request, as of today. Nothing about the policy: applying it is the agent's job | `src/plugin/requirements.py`, `src/plugin/guide.py` |
| `get_trip` | Begins a booking run for a request: the visit as booked today (airports, assignment dates and length, family status, housing, approval, last visit, days since the previous visit, flight days, days before departure, estimated driving miles) and its `run_id` | `src/plugin/trip.py` |
| `search_flights` | The round-trip offers out on one day and back on another (0 to 30 days later, today or later): airline, ticket type, cabin, refundability, fare and every flight | `src/plugin/search.py` |
| `solve_booking` | The answer key: the visit as booked today, its offers and the refusal or booking the rules require. NanoAgent runs it before the agent, out of its sight; it is never one of the agent's tools | `src/plugin/solve.py` |

### Tasks

| Task | Does | Runner |
|---|---|---|
| `booking-requirements` | Shows what to tell us to book a home visit (topic `ALL`, `FIELDS` or `AIRPORTS`) | `tool`, with `booking_requirements` |
| `search-flights` | Shows the round-trip offers on a route and days | `tool`, with `search_flights` |
| `energy-corporate-flight-booking` | Refuses or books a return home visit under the policy | `agent`, with `get_trip` and `search_flights`; reference `solve_booking` |

The booking task's input is the visit request, which the chat fills from plain words such as "I'm on a
temporary assignment in Houston from Sep 1 to Feb 28, single, I still keep my place in Denver, I last went
home Nov 2 and my manager approved this one: book me home Dec 4, back Dec 7": `traveller_name`,
`tda_airport` and `home_airport` (U.S. airport codes from the list), `assignment_start` and
`assignment_end`, `family_status` (`SINGLE`, `UNACCOMPANIED` or `ACCOMPANIED`),
`duplicate_housing_obligation` (still keeps the home), `last_home_visit` (empty when none yet),
`manager_approved`, `outbound_date` and `return_date`. Flight dates are local dates at the airport the flight
leaves from: `outbound_date` at the assignment airport, `return_date` at the home airport; every rule on
them (the visit's days, C6, C7, C8) uses those local dates. The booking date is today (UTC), read when the answer
key is pinned; the assignment and the last visit may be in the past, but flights leaving before today or
returning more than 330 days ahead are refused.

The agent's path is at most three tool calls: `get_trip` with the request, `search_flights` from the
assignment airport to the home airport on the visit's days (skipped when rules C1-C8 already refuse the
visit), then `submit`. It submits `run_id`, `booked`, `refusal` and `offer_id`.

### The rules (the task's instructions state them exactly)

| Rule | Policy text it formalises | Exact rule |
|---|---|---|
| C1 | "The up-to-12 months TDA covers an assignment period that lasts between 91 days and one year (365 days)"; "Shorter assignments will be treated as business trips" | `assignment_days` (first and last day included) is 91 to 365, else `NOT_A_TDA` |
| C2 | "Return home visits apply only if you have a duplicate housing obligation" | Else `NO_DUPLICATE_HOUSING` |
| C3 | "Accompanied (Family status): None" | `ACCOMPANIED` is refused |
| C4 | "Actual return travel... requires the approval of your direct supervisor or manager" | Else `NO_MANAGER_APPROVAL` |
| C5 | "Airfare... if the distance between locations is 400 miles or greater" | `estimated_driving_miles` ≥ 400 (exactly 400 is fine), else `UNDER_400_MILES` |
| C6 | Return visits are trips "from your TDA location to your primary residence" during the TDA | Outbound and return days (local departure dates) within the assignment, else `OUTSIDE_ASSIGNMENT` |
| C7 | "Single: Return trip not more than once every four weeks; Unaccompanied: ... once every two weeks" | Outbound (its local departure date) at least 28 (single) or 14 (unaccompanied) days after the last home visit, or the assignment start when none (exactly 28 or 14 is fine), else `TOO_SOON` |
| C8 | "Airfare (round trip/economy class/non-refundable/14-day advance purchase only)" | Outbound (its local departure date at the assignment airport) at least 14 days after the booking date (exactly 14 is fine), else `UNDER_14_DAYS_ADVANCE` |
| C9 | The same | Only a `ROUND_TRIP` ticket in `ECONOMY` that is not refundable; none: `NO_COMPLIANT_FLIGHT` |
| C10 | (The policy defers to Chevron Policy 585, which is not public) | The lowest compliant fare; ties all pass |

**Distance.** The policy measures distance by "the most direct ground travel route" between the two
residences. The plugin estimates it from the airports: great-circle miles × 1.2, a common U.S. road
circuity factor (Ballou, Rahardja & Sakai, 2002, "Selected country circuity factors for road travel
distance estimation", *Transportation Research Part A* 36(9)). `get_trip` shows the estimate, and the
verifier recomputes it with the same code.

Out of scope: business trips home counting toward the frequency, combining visits with business travel,
management changing the frequency, a spouse visiting instead, emergency home visits, travel to and from
the assignment itself, mileage when driving, and the booking channel and payment card. Every other TDA
benefit (allowances, housing, shipment, taxes) is out of scope too.

### The simulated flights

`src/plugin/world.py` (the same file as `verifier/world.py`) makes the one-way flights on a route and day
from a SHA-256 stream keyed by the route and the day only, and the round-trip fares by the route and both
days, so a search gives the same offers on every machine and on any booking date, and the verifier rebuilds
every search the agent made. Its model, every constant of which is a modelling choice, not data:

- **Airports:** the 31 large U.S. airports of an OurAirports snapshot (public domain), fetched 2026-11-02,
  with their standard-time UTC offsets (no daylight saving). A flight's day is the local date at the
  airport it leaves from, and every airport has departures from 06:00 to 21:55 local time on it. Segment
  `depart` and `arrive` are UTC; `depart_local` is the departure in local time at the segment's origin, so
  a 19:00 departure from Los Angeles on Dec 4 is `2026-12-05 03:00` UTC and still flies on Dec 4.
- **Airlines:** six real U.S. airlines (Delta, United, American, Alaska, JetBlue, Southwest), each with its
  hubs among the airports, longest nonstop and premium cabin. An airline sells a nonstop when one end is its
  hub, and connections through its own hubs that add at most 35% distance. Each route has up to three
  itineraries, the same every day and in both directions; each flies on 95% of days. Flight numbers (e.g.
  `UA 1482`) are stable per airline and leg.
- **Times:** minutes in the air are 20 + the great-circle distance at 870 km/h; connections take 45 to 240
  minutes.
- **Fares:** a one-way economy fare is $50 + 30 x km^0.85 cents, times 0.80-1.35 by day, connections 78-95%
  of that, and low-cost airlines 88%. An airline flying both ways sells a round trip: non-refundable economy
  at 90-102% of its two one-way fares; refundable economy at 1.25-2.1x (on 85% of trips); and its premium
  cabin (first; JetBlue's business on flights of 3,500 km or more) at 1.7-3.2x, sometimes a 1.08-1.35x sale,
  refundable or not. On 45% of searches two separate one-way tickets (the cheapest each way, possibly two
  airlines) are sold too, at 82-108% of their fares, so they are sometimes the cheapest offer.

Exact boundaries of the distance (exactly 400 miles) and of fares (exact ties, one cent more) rarely occur
in realistic data, so the tests and scripted cases check them with a hand-built world, which replaces the
offers or the distance in the tools and the verifier alike. Date boundaries use the real simulated offers.

## Layout

It has the standard plugin layout, which NanoAgent requires:

```text
.
├── nanoagent.yaml   # manifest: id, runtime, permissions (no network), tools, tasks and their instructions
├── contract.py      # each tool's and task's typed input and output: slimconfig Output classes
├── README.md
├── LICENSE
├── pyproject.toml
├── uv.lock
├── .gitignore
├── .env             # needed environment variable names (none)
├── src/plugin/      # the MCP server (__main__.py, IMPLEMENTATIONS) and the tools
│   ├── world.py     # airports, airlines, the simulated offers, driving miles and the trip a request makes;
│   │                #   the same file as verifier/world.py
│   ├── rules.py     # requests, dates and rules C1-C10 as exact integer code; the same file as verifier/rules.py
│   ├── guide.py     # what a home-visit request must give; the same file as verifier/guide.py
│   └── receipts.py  # each run's receipts in the workspace: runs/<run id>/trip.json, search-<n>.json
├── tests/           # rules, world, requirements, verifier, scripted cases (tests/cases/*.json), MCP server
├── ui/              # renderers.js / renderers.css: the requirements, the offers table, the answer
├── product/         # product.yaml and icon.svg
└── verifier/        # the deterministic verifier: one module per tool and booking.py for the task
```

The verdict of the booking task is a list of named checks, each with `ok`, `expected`, `actual` and a
message naming the offer or the fact and the rule:

- integrity gates: `answer-key` (the pinned key is this request's, booked on the day it was pinned, with
  the route's offers, and follows the rules), `this-run` (the submitted run was begun by `get_trip` for
  this request, on the same booking date, after the key was pinned), `searched` (before booking or finding
  no compliant fare), `receipts-match` (every search receipt equals the route's offers for its query,
  rebuilt by the verifier), `offer-seen` (the booked offer was in this run's search results, from the
  assignment home and back);
- policy: `refusal` (book, or the first rule's refusal), `dates`, `ticket`, `cabin`, `refundable`, `fare`.

The verdict is valid, scoring 1, only when every check holds; any failed check scores 0, since an answer
either follows the policy or it does not. Checks after a failed one they depend on are "not checked".
Expected values come from the verifier's own copy of the rules applied to the pinned trip and offers.

## Develop and run

```bash
uv sync --extra dev
uv run pytest
uv run ruff check .
```

The tests freeze today at 2026-11-05, so they pass on any day. `uv run pytest` replays the scripted cases
in `tests/cases/` (gold, wrong, missing, malformed, tampered and boundary runs) through the real tools and
verifier, checks the answer key against an independent reading of the rules for 500 varied requests, and
checks the simulated world's plausibility, determinism and size.

NanoAgent passes the folder the plugin may write to as `NANOAGENT_WORKSPACE`; the tools write only
their receipts there, under `runs/`. To check the plugin with NanoAgent from its checkout:

```bash
uv run nanoagent plugin inspect <path to this plugin>
```

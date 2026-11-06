// How this plugin's page draws its tasks' outputs: what to tell us to book a home visit (fields, date rules,
// airports), the round-trip offers as a table, and a booking as the chosen offer or the reason nothing was booked.
import { dataTable, disclosure, h, plural, statusPill } from "./kit/components.js";

const money = (cents) => `$${(cents / 100).toFixed(2)}`;

const REASONS = {
  NOT_A_TDA: "The assignment is not 91-365 days long",
  NO_DUPLICATE_HOUSING: "No home is kept during the assignment",
  ACCOMPANIED: "Accompanied travellers get no home visits",
  NO_MANAGER_APPROVAL: "The manager has not approved the visit",
  UNDER_400_MILES: "Under 400 miles apart: drive instead",
  OUTSIDE_ASSIGNMENT: "The visit is not within the assignment",
  TOO_SOON: "Too soon after the previous visit",
  UNDER_14_DAYS_ADVANCE: "Less than 14 days before departure",
  NO_COMPLIANT_FLIGHT: "No round-trip, economy, non-refundable fare",
};

function facts(rows) {
  return h(
    "dl",
    { class: "trip-facts" },
    rows.map(([label, value]) => [h("dt", { text: label }), h("dd", { text: value })]),
  );
}

function fieldsTable(fields) {
  return dataTable({
    columns: [
      { key: "name", label: "Field", primary: true },
      { key: "kind", label: "Takes" },
      { key: "example", label: "Example" },
      { key: "description", label: "Meaning" },
    ],
    rows: fields,
    caption: "What to tell us",
    empty: "No fields.",
  }).element;
}

function airportsTable(airports) {
  return dataTable({
    columns: [
      { key: "code", label: "Code", primary: true },
      { key: "city", label: "City" },
      { key: "name", label: "Airport" },
    ],
    rows: airports,
    sort: { key: "code" },
    caption: "Airports",
    empty: "No airports.",
  }).element;
}

function requirements(answer) {
  const parts = [h("p", { class: "muted", text: `Booking as of today, ${answer.today}` })];
  if (answer.fields.length) parts.push(fieldsTable(answer.fields));
  if (answer.date_rules.length) {
    parts.push(h("h4", { text: "Dates" }), h("ul", { class: "rules" }, answer.date_rules.map((rule) => h("li", { text: rule }))));
  }
  parts.push(h("h4", { text: "For example" }), h("blockquote", { class: "example", text: answer.example_request }));
  if (answer.airports.length) {
    parts.push(disclosure({ summary: plural(answer.airports.length, "airport"), open: !answer.fields.length }, airportsTable(answer.airports)));
  }
  return h("div", { class: "requirements" }, parts);
}

function leg(segments) {
  const stops = segments.map((segment) => segment.origin).concat(segments.at(-1).destination);
  return `${stops.join(" → ")}, leaves ${segments[0].depart_local} local (${segments[0].depart} UTC), arrives ${segments.at(-1).arrive} UTC`;
}

function offersTable(offers) {
  return dataTable({
    columns: [
      { key: "offer_id", label: "Offer", primary: true },
      { key: "carrier", label: "Airline" },
      { key: "ticket", label: "Ticket", value: (o) => (o.ticket === "ROUND_TRIP" ? "round trip" : "two one-ways") },
      { key: "cabin", label: "Cabin", value: (o) => o.cabin.toLowerCase() },
      { key: "refundable", label: "Refundable", value: (o) => (o.refundable ? "yes" : "no") },
      { key: "fare_cents", label: "Fare", numeric: true, render: (o) => money(o.fare_cents) },
      { key: "out", label: "Out", value: (o) => leg(o.outbound) },
      { key: "back", label: "Back", value: (o) => leg(o.inbound) },
    ],
    rows: offers,
    sort: { key: "fare_cents" },
    caption: "Round-trip offers",
    empty: "No offers on this route and these days.",
  }).element;
}

export default {
  RequirementsOutput: requirements,
  SearchOutput: ({ note, offers }) =>
    h(
      "div",
      { class: "offers" },
      h("p", { class: "muted", text: `${plural(offers.length, "offer")}. ${note}` }),
      offersTable(offers),
    ),
  BookingOutput: (booking) =>
    booking.booked
      ? h(
          "div",
          { class: "booking" },
          statusPill(`Booked ${booking.offer_id}`, "ok", { icon: true }),
          facts([["Run", booking.run_id]]),
        )
      : h(
          "div",
          { class: "booking" },
          statusPill("Not booked", "warn", { icon: true }),
          facts([
            ["Reason", REASONS[booking.refusal] ?? booking.refusal],
            ["Run", booking.run_id],
          ]),
        ),
};

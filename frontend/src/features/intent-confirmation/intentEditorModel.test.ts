import assert from "node:assert/strict";
import test from "node:test";
import {
  buildIntentEditIdempotencyKey,
  buildIntentStructuredOverrides,
  emptyIntentEditForm,
} from "./intentEditorModel";

test("typed intent editor serializes boundaries, windows, events, budget, needs, and candidate preferences", () => {
  const form = emptyIntentEditForm();
  form.city = "上海";
  form.tripDays = "3";
  form.startDate = "2026-08-01";
  form.timezone = "Asia/Shanghai";
  form.arrival = {
    localDatetime: "2026-08-01T12:00",
    timezone: "Asia/Shanghai",
    flexibilityMinutes: "15",
    locationText: "虹桥站",
  };
  form.departure = {
    localDatetime: "2026-08-03T20:00",
    timezone: "Asia/Shanghai",
    flexibilityMinutes: "0",
    locationText: "浦东机场",
  };
  form.availabilityWindows = [{
    id: "window-1",
    date: "2026-08-02",
    startTime: "14:00",
    endTime: "16:00",
    timezone: "Asia/Shanghai",
    crossesMidnight: false,
  }];
  form.fixedEvents = [{
    id: "booking-1",
    title: "人民广场预约",
    startAt: "2026-08-02T14:00",
    endAt: "2026-08-02T16:00",
    timezone: "Asia/Shanghai",
    fixedDay: "2",
    placeCandidateId: "cand_booking_place",
    locationText: "人民广场",
    flexibility: "fixed",
  }];
  form.mustCandidateIds = ["cand_must"];
  form.optionalCandidateIds = ["cand_optional"];
  form.avoidCandidateIds = ["cand_avoid"];
  form.budget = { amountMinor: "250000", currency: "cny", scope: "total", level: "medium", flexibilityPercent: "10" };
  form.travelerNeeds = [{ id: "need-1", needType: "mobility", description: "Avoid long walking stretches", severity: "required" }];

  const payload = buildIntentStructuredOverrides(form);

  assert.equal(payload.arrival_boundary?.local_datetime, "2026-08-01T12:00:00");
  assert.equal(payload.departure_boundary?.location_text, "浦东机场");
  assert.deepEqual(payload.availability_windows[0], {
    date: "2026-08-02",
    start_time: "14:00",
    end_time: "16:00",
    timezone: "Asia/Shanghai",
    crosses_midnight: false,
  });
  assert.equal(payload.fixed_events[0]?.name, "人民广场预约");
  assert.equal(payload.fixed_events[0]?.place_candidate_id, "cand_booking_place");
  assert.deepEqual(payload.must_candidate_ids, ["cand_must"]);
  assert.equal(payload.budget?.amount_minor, 250000);
  assert.equal(payload.budget?.currency, "CNY");
  assert.deepEqual(payload.traveler_needs[0], {
    type: "traveler_need",
    need: "Avoid long walking stretches",
    need_type: "mobility",
    severity: "required",
  });
});

test("typed intent editor rejects incomplete authoritative boundaries and budget", () => {
  const form = emptyIntentEditForm();
  form.arrival.locationText = "虹桥站";
  assert.throws(() => buildIntentStructuredOverrides(form), /Arrival date and time/);

  const budgetForm = emptyIntentEditForm();
  budgetForm.budget.amountMinor = "100000";
  assert.throws(() => buildIntentStructuredOverrides(budgetForm), /Budget currency/);
});

test("intent edit idempotency keys are bounded and depend on structured values", () => {
  const payload = buildIntentStructuredOverrides(emptyIntentEditForm());
  const first = buildIntentEditIdempotencyKey("intent_1", "rev_1", payload);
  const second = buildIntentEditIdempotencyKey("intent_1", "rev_1", { ...payload, city: "上海" });
  assert.ok(first.startsWith("intent-edit:intent_1:rev_1:"));
  assert.ok(first.length <= 180);
  assert.notEqual(first, second);
});

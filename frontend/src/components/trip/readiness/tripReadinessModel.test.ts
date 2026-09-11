import { strict as assert } from "node:assert";
import { test } from "node:test";
import { buildTripReadinessViewModel } from "./tripReadinessModel";

const baseDays = [
  {
    day: 1,
    blocks: [
      { block_type: "morning", items: ["a"] },
      { block_type: "afternoon", items: ["b"] },
      { block_type: "evening", items: ["c"] },
    ],
  },
];

test("marks complete trips without major risks as ready", () => {
  const model = buildTripReadinessViewModel({
    city: "杭州",
    tripDays: 1,
    days: baseDays,
    completion: {
      trip_completeness: 94,
      action_tasks: [],
      sparse_blocks_detected: [],
      auto_filled_scenic_count: 1,
      auto_filled_meal_count: 1,
      auto_filled_evening_count: 1,
      why_this_plan_works: ["路线密度、餐食和夜间收口都已成形。"],
    },
    plannerRealism: { status: "executable", headline: "路线基本可走", issues: [] },
  });

  assert.equal(model.status, "ready");
  assert.equal(model.primaryIssue, undefined);
});

test("keeps minor gaps distinct from severe readiness failures", () => {
  const model = buildTripReadinessViewModel({
    city: "杭州",
    tripDays: 1,
    days: baseDays,
    completion: {
      trip_completeness: 82,
      action_tasks: [],
      sparse_blocks_detected: ["Day 1 evening"],
      auto_filled_scenic_count: 0,
      auto_filled_meal_count: 0,
      auto_filled_evening_count: 0,
    },
    plannerRealism: { status: "executable", headline: "路线可走但有留白", issues: [] },
  });

  assert.equal(model.status, "minor-gaps");
});

test("elevates obvious sparse schedules to needs attention", () => {
  const model = buildTripReadinessViewModel({
    city: "杭州",
    tripDays: 1,
    days: baseDays,
    completion: {
      trip_completeness: 68,
      action_tasks: [],
      sparse_blocks_detected: ["Day 1 morning", "Day 1 afternoon", "Day 1 evening"],
      auto_filled_scenic_count: 0,
      auto_filled_meal_count: 0,
      auto_filled_evening_count: 0,
    },
  });

  assert.equal(model.status, "needs-attention");
  assert.equal(model.primaryIssue?.title, "存在未补齐时间段");
});

test("planner realism high warnings make the trip not ready", () => {
  const model = buildTripReadinessViewModel({
    city: "杭州",
    tripDays: 1,
    days: baseDays,
    completion: {
      trip_completeness: 92,
      action_tasks: [],
      sparse_blocks_detected: [],
      auto_filled_scenic_count: 0,
      auto_filled_meal_count: 0,
      auto_filled_evening_count: 0,
    },
    plannerRealism: {
      status: "unstable",
      headline: "跨区移动过重",
      issues: [{ severity: "high", title: "移动不可行", detail: "上午到下午路线跨度过大。", day: 1 }],
    },
  });

  assert.equal(model.status, "not-ready");
  assert.equal(model.primaryIssue?.severity, "high");
  assert.deepEqual(model.priorityAction, {
    kind: "focus-day",
    day: 1,
    label: "查看 Day 1 路线",
  });
});

test("protected boundaries are surfaced when fixed events exist", () => {
  const model = buildTripReadinessViewModel({
    city: "西安",
    tripDays: 2,
    days: baseDays,
    planningAssumptions: { fixed_event_count: 2, availability_window_count: 1 },
    boundaryExplanation: {
      arrival_anchor_influenced: true,
      arrival_anchor_name: "西安北站",
      departure_anchor_influenced: true,
      departure_anchor_name: "西安站",
    },
  });

  assert.ok(model.protectedBoundaries.some((boundary) => boundary.key === "fixed-events"));
  assert.ok(model.protectedBoundaries.some((boundary) => boundary.key === "arrival-anchor"));
});

test("works when backend completion intelligence is absent", () => {
  const model = buildTripReadinessViewModel({
    city: "上海",
    tripDays: 1,
    days: [{ day: 1, blocks: [{ block_type: "morning", items: [] }] }],
  });

  assert.equal(model.status, "minor-gaps");
  assert.equal(model.primaryIssue?.key, "fallback-density-day-1");
});

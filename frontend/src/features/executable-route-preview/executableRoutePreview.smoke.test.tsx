import assert from "node:assert/strict";
import test from "node:test";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { ExecutableRoutePreview } from "./ExecutableRoutePreview";

const componentPath = fileURLToPath(new URL("./ExecutableRoutePreview.tsx", import.meta.url));

const itinerary = {
  trip_days: 1,
  planner_realism: {
    daily_loads: [{ day: 1, classification: "balanced" as const, activity_count: 1, fixed_count: 0, activity_minutes: 120, travel_minutes: 30, route_distance_m: 6400, reason_codes: ["daily_load_balanced"], explanation: "服务端已根据活动和移动时间完成负载判定。" }],
  },
  days: [{ day: 1, blocks: [{ block_type: "morning" as const, start_time: "09:00", end_time: "12:00", items: [{ name: "西湖", type: "scenic" as const, start_time: "09:00", end_time: "11:00", is_fixed: false, travel_from_name: "杭州东站", travel_duration_s: 1800, travel_distance_m: 6400, placement_reason: "把第一站放在上午，给后续行程留出余量。" }] }], }],
};

test("route preview renders a readable day timeline without internal handoff metadata", () => {
  const html = renderToStaticMarkup(<ExecutableRoutePreview itinerary={itinerary} variant="draft" />);
  assert.match(html, /你的第一版行程/);
  assert.match(html, /预计移动/);
  assert.match(html, /活动时长/);
  assert.match(html, /为什么这样安排/);
  assert.doesNotMatch(html, /trace_digest/);
  assert.doesNotMatch(html, /handoff ID/);
});

test("saved route preview uses the existing server-authoritative proposal endpoints", () => {
  const source = readFileSync(componentPath, "utf8");
  assert.match(source, /previewPersistedMutation/);
  assert.match(source, /applyPersistedMutationProposal/);
  assert.match(source, /X-Idempotency-Key/);
  assert.match(source, /固定安排没有移动/);
  assert.match(source, /没有重新生成全部行程/);
});

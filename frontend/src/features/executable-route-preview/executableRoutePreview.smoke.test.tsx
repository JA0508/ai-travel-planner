import assert from "node:assert/strict";
import test from "node:test";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { ExecutableRoutePreview } from "./ExecutableRoutePreview";
import type { RoutePreviewItinerary } from "./routePreviewModel";

const componentPath = fileURLToPath(new URL("./ExecutableRoutePreview.tsx", import.meta.url));

const itinerary: RoutePreviewItinerary = {
  trip_days: 1,
  planning_anchor_source: {
    source_type: "arrival_anchor",
    source_name: "杭州东站",
    latitude: 30.293,
    longitude: 120.212,
  },
  planner_realism: {
    daily_loads: [{ day: 1, classification: "balanced" as const, activity_count: 1, fixed_count: 0, activity_minutes: 120, travel_minutes: 30, route_distance_m: 6400, reason_codes: ["daily_load_balanced"], explanation: "服务端已根据活动和移动时间完成负载判定。" }],
  },
  days: [{ day: 1, blocks: [{ block_type: "morning" as const, start_time: "09:00", end_time: "12:00", items: [{ stable_id: "west-lake", name: "西湖", type: "scenic" as const, city: "杭州", latitude: 30.235, longitude: 120.148, start_time: "09:00", end_time: "11:00", duration_minutes: 120, is_fixed: false, source_type: "user_seed" as const, source_label: "必去", travel_from_name: "杭州东站", travel_duration_s: 1800, travel_distance_m: 6400, travel_data_status: "confirmed" as const, placement_reason: "把第一站放在上午，给后续行程留出余量。" }] }], }],
};

test("route preview renders a readable day timeline without internal handoff metadata", () => {
  const html = renderToStaticMarkup(<ExecutableRoutePreview itinerary={itinerary} variant="draft" />);
  assert.match(html, /你的第一版行程/);
  assert.match(html, /预计移动/);
  assert.match(html, /活动时长/);
  assert.match(html, /为什么这样安排/);
  assert.match(html, /data-route-surface="roadbook"/);
  assert.match(html, /路程已确认/);
  assert.doesNotMatch(html, /trace_digest/);
  assert.doesNotMatch(html, /handoff ID/);
});

test("saved route uses an on-the-road workspace vocabulary", () => {
  const saved = structuredClone(itinerary);
  saved.days[0].blocks[0].items[0].is_fixed = true;
  saved.days[0].blocks[0].items[0].placement_reason = "Reused canonical coordinates from the intent handoff.";
  const html = renderToStaticMarkup(<ExecutableRoutePreview itinerary={saved} variant="saved" tripId="trip-1" baseRevisionId="revision-1" onApplied={() => undefined} />);
  assert.match(html, /带着这份路线上路/);
  assert.match(html, /LIVING ROADBOOK/);
  assert.match(html, /DAY 01/);
  assert.match(html, /LOCKED/);
  assert.match(html, /已经留好的时间/);
  assert.match(html, /不会被随意移动/);
  assert.match(html, /帮我松一点/);
  assert.match(html, /data-route-map-pane="true"/);
  assert.match(html, /data-roadbook-layout="living"/);
  assert.doesNotMatch(html, /class="erp-risks"/);
  assert.doesNotMatch(html, /TripRevision/);
  assert.doesNotMatch(html, /mutation/);
  assert.doesNotMatch(html, /canonical|handoff/i);
  assert.doesNotMatch(html, /NEXT_PUBLIC_AMAP_WEB_KEY/);
  assert.doesNotMatch(html, /仍可继续编辑路线/);
});

test("saved route preview sends only a user goal to the server-authoritative repair endpoint", () => {
  const source = readFileSync(componentPath, "utf8");
  assert.match(source, /previewLocalRelaxDayRepair/);
  assert.match(source, /applyPersistedMutationProposal/);
  assert.match(source, /X-Idempotency-Key/);
  assert.match(source, /固定安排没有移动/);
  assert.match(source, /没有重新生成全部行程/);
  assert.match(source, /target_day: day, goal: "relax_day"/);
  assert.match(source, /调整前/);
  assert.match(source, /系统补充/);
  assert.match(source, /暂时没有可验证的安排说明/);
  assert.doesNotMatch(source, /buildDayRelaxationPlan/);
  assert.doesNotMatch(source, /move_stop/);
});

test("route preview does not present unavailable route data as a confirmed leg", () => {
  const unavailable = structuredClone(itinerary);
  const item = unavailable.days[0].blocks[0].items[0];
  item.travel_duration_s = null;
  item.travel_distance_m = null;
  item.travel_data_status = "unavailable";
  const html = renderToStaticMarkup(<ExecutableRoutePreview itinerary={unavailable} variant="draft" />);
  assert.match(html, /路线待确认/);
  assert.match(html, /暂时无法确认这段路程/);
  assert.doesNotMatch(html, /路线待确认[^]*?<small>0 分钟/);
});

test("saved roadbook preserves unavailable route uncertainty", () => {
  const unavailable = structuredClone(itinerary);
  const item = unavailable.days[0].blocks[0].items[0];
  item.travel_duration_s = null;
  item.travel_distance_m = null;
  item.travel_data_status = "unavailable";
  const html = renderToStaticMarkup(<ExecutableRoutePreview itinerary={unavailable} variant="saved" />);
  assert.match(html, /这段路线还没有确认/);
  assert.match(html, /不会把缺失的路程当作 0 分钟/);
  assert.doesNotMatch(html, /路线已确认/);
  assert.doesNotMatch(html, /VERIFIED PLACE/);
});

import assert from "node:assert/strict";
import test from "node:test";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { ExecutableRoutePreview } from "./ExecutableRoutePreview";
import type { RoutePreviewItinerary } from "./routePreviewModel";

const componentPath = fileURLToPath(new URL("./ExecutableRoutePreview.tsx", import.meta.url));
const repairPreviewPath = fileURLToPath(new URL("./RoadbookRepairPreview.tsx", import.meta.url));
const repairModelPath = fileURLToPath(new URL("./repairPreviewModel.ts", import.meta.url));

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
  assert.match(html, /这份行程已保存为正式路线/);
  assert.match(html, /role="status"/);
  assert.match(html, /已保存为正式路线。可以继续调整。/);
  assert.match(html, /LIVING ROADBOOK/);
  assert.match(html, /DAY 01/);
  assert.match(html, /LOCKED/);
  assert.match(html, /已经留好的时间/);
  assert.match(html, /不会被随意移动/);
  assert.doesNotMatch(html, /帮我松一点/);
  assert.match(html, /data-route-map-pane="true"/);
  assert.match(html, /data-roadbook-layout="living"/);
  assert.doesNotMatch(html, /class="erp-risks"/);
  assert.doesNotMatch(html, /TripRevision/);
  assert.doesNotMatch(html, /mutation/);
  assert.doesNotMatch(html, /canonical|handoff/i);
  assert.doesNotMatch(html, /NEXT_PUBLIC_AMAP_WEB_KEY/);
  assert.doesNotMatch(html, /仍可继续编辑路线/);
});

test("saved route offers local repair only for a rushed day", () => {
  const rushed = structuredClone(itinerary);
  const dailyLoads = rushed.planner_realism?.daily_loads;
  assert.ok(dailyLoads?.[0]);
  dailyLoads[0].classification = "rushed";
  const html = renderToStaticMarkup(<ExecutableRoutePreview itinerary={rushed} variant="saved" tripId="trip-1" baseRevisionId="revision-1" onApplied={() => undefined} />);

  assert.match(html, /今天稍微赶了一点/);
  assert.match(html, /帮我松一点/);
});

test("saved route preview sends only a user goal to the server-authoritative repair endpoint", () => {
  const source = `${readFileSync(componentPath, "utf8")}\n${readFileSync(repairPreviewPath, "utf8")}\n${readFileSync(repairModelPath, "utf8")}`;
  assert.match(source, /previewLocalRelaxDayRepair/);
  assert.match(source, /applyPersistedMutationProposal/);
  assert.match(source, /undoPersistedRevision/);
  assert.match(source, /X-Idempotency-Key/);
  assert.match(source, /路线刚刚发生了变化/);
  assert.match(source, /你的原路线仍然保持不变/);
  assert.match(source, /target_day: day, goal: "relax_day"/);
  assert.match(source, /应用这次调整/);
  assert.match(source, /保持原路线/);
  assert.match(source, /撤销刚才的调整/);
  assert.match(source, /重试撤销/);
  assert.match(source, /errorMessage/);
  assert.match(source, /proposal\.commands/);
  assert.match(source, /previewRequestIdRef/);
  assert.match(source, /requestId !== previewRequestIdRef\.current/);
  assert.match(source, /tabIndex=\{-1\}/);
  assert.match(source, /rootRef\.current\?\.focus/);
  assert.match(source, /暂时没有可验证的安排说明/);
  assert.doesNotMatch(source, /buildDayRelaxationPlan/);
  assert.doesNotMatch(source, /commands\s*:\s*\[/);
  assert.doesNotMatch(source, /Apply mutation|Commit revision|Accept patch/);
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

test("saved roadbook presents a system lunch as a route stop and a meal gap as a field note", () => {
  const mealAware = structuredClone(itinerary);
  mealAware.days[0].blocks.push({
    block_type: "afternoon",
    start_time: "13:00",
    end_time: "17:00",
    items: [{
      stable_id: "amap:fixture-lunch",
      name: "茶人村",
      type: "restaurant",
      city: "杭州",
      latitude: 30.229,
      longitude: 120.111,
      start_time: "12:15",
      end_time: "13:15",
      duration_minutes: 60,
      is_fixed: false,
      source_type: "auto_seeded_meal",
      source_label: "系统补充",
      source_reason: "系统为这一天补上的午饭。",
      meal_role: "lunch",
      travel_from_name: "西湖",
      travel_duration_s: 600,
      travel_distance_m: 700,
      travel_data_status: "confirmed",
      travel_provider: "amap",
      placement_reason: "前后路线都已确认，并为后面的安排留出时间。",
    }],
  });
  mealAware.meal_rhythm = {
    policy_version: "meal-rhythm-v1",
    days: [{
      day: 1,
      slots: [
        { role: "lunch", status: "auto_completed", window_start: "11:30", window_end: "14:00", scheduled_item_name: "茶人村", explanation: "系统已把茶人村安排为午饭。" },
        { role: "dinner", status: "unresolved", window_start: "17:30", window_end: "20:30", explanation: "晚饭还没找到合适的时间和真实地点。" },
      ],
      field_notes: ["晚饭还没找到合适的位置；系统没有硬塞一个未经验证的餐饮点。"],
    }],
  };

  const html = renderToStaticMarkup(<ExecutableRoutePreview itinerary={mealAware} variant="saved" />);

  assert.match(html, /LUNCH \/ 午饭/);
  assert.match(html, /系统为这一天补上的午饭/);
  assert.match(html, /MEAL NOTE/);
  assert.match(html, /晚饭还没找到合适的位置/);
  assert.doesNotMatch(html, /MEAL_CONSTRAINT_UNRESOLVED/);
});

import test from "node:test";
import assert from "node:assert/strict";
import { buildDayLoads, shouldDisplayTravelLeg } from "./routePreviewModel";

const itinerary = {
  trip_days: 2,
  planner_realism: {
    daily_loads: [
      { day: 1, classification: "rushed" as const, activity_count: 5, fixed_count: 1, activity_minutes: 425, travel_minutes: 75, route_distance_m: 3600, reason_codes: ["daily_load_high"], explanation: "服务端判定当天衔接偏紧。" },
      { day: 2, classification: "relaxed" as const, activity_count: 0, fixed_count: 0, activity_minutes: 0, travel_minutes: 0, route_distance_m: null, reason_codes: ["daily_load_light"], explanation: "服务端判定当天留有余量。" },
    ],
  },
  days: [
    { day: 1, blocks: [{ block_type: "morning" as const, start_time: "09:00", end_time: "12:00", items: [
      { stable_id: "fixed", name: "博物馆预约", type: "scenic" as const, start_time: "09:00", end_time: "10:30", duration_minutes: 90, is_fixed: true, source_type: "user_fixed" as const },
      { stable_id: "must", name: "一定想去", type: "scenic" as const, start_time: "10:45", end_time: "12:00", duration_minutes: 75, is_fixed: false, source_type: "user_seed" as const, travel_duration_s: 900 },
    ] }, { block_type: "afternoon" as const, start_time: "13:00", end_time: "18:00", items: [
      { stable_id: "optional", name: "系统补入街区", type: "scenic" as const, start_time: "13:00", end_time: "15:00", duration_minutes: 120, is_fixed: false, source_type: "auto_seeded_poi" as const, travel_duration_s: 1800 },
      { stable_id: "meal", name: "系统补入晚餐", type: "restaurant" as const, start_time: "15:30", end_time: "17:00", duration_minutes: 90, is_fixed: false, source_type: "auto_seeded_meal" as const, travel_duration_s: 1800 },
      { stable_id: "fill", name: "系统补点", type: "scenic" as const, start_time: "17:10", end_time: "18:00", duration_minutes: 50, is_fixed: false, source_type: "auto_filled" as const, travel_duration_s: 1800 },
    ] }] },
    { day: 2, blocks: [{ block_type: "morning" as const, start_time: "09:00", end_time: "12:00", items: [] }, { block_type: "afternoon" as const, start_time: "13:00", end_time: "18:00", items: [] }] },
  ],
};

test("classifies a packed day from the server-owned realism payload", () => {
  const [day] = buildDayLoads(itinerary);
  assert.equal(day.pace, "rushed");
  assert.equal(day.activityMinutes, 425);
  assert.equal(day.travelMinutes, 75);
});

test("does not present an internal route-center anchor as a traveler leg", () => {
  const item = {
    name: "灵隐寺",
    type: "scenic" as const,
    start_time: "09:00",
    end_time: "10:30",
    is_fixed: false,
    travel_from_name: "灵隐寺附近路线中心",
    travel_data_status: "confirmed" as const,
    travel_duration_s: 0,
    travel_distance_m: 1,
  };

  assert.equal(shouldDisplayTravelLeg({ planning_anchor_source: { source_type: "route_centroid", source_name: "灵隐寺附近路线中心" } }, item), false);
  assert.equal(shouldDisplayTravelLeg({ planning_anchor_source: { source_type: "arrival_anchor", source_name: "杭州东站" } }, { ...item, travel_from_name: "杭州东站" }), true);
  assert.equal(shouldDisplayTravelLeg({ planning_anchor_source: { source_type: "provided_hotel", source_name: "路线中心酒店" } }, { ...item, travel_from_name: "路线中心酒店" }), true);
});

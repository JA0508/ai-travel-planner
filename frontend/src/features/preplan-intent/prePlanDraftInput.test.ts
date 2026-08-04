import assert from "node:assert/strict";
import test from "node:test";
import { buildPrePlanDraftText, buildPrePlanDraftTextFromCompilerIntent } from "./prePlanDraftInput";

test("structured entry becomes labelled source text for the same pre-plan contract", () => {
  const text = buildPrePlanDraftText({
    directText: "我要去上海。",
    tripDays: "3",
    scenicSpots: ["外滩", "上海博物馆"],
    restaurants: ["本地小吃"],
    fixedEventsText: "活动 | 人民广场 | 2 | 14:00 | 16:00",
    availabilityWindowsText: "1 | first day partial | 12:00 | 21:00",
    arrivalAnchor: "虹桥站",
    departureAnchor: "浦东机场",
    hotel: "",
    preferences: ["轻松", "夜景"],
    pacingLabel: "平衡节奏",
    travelMode: "metro",
  });

  assert.match(text, /行程天数：3 天/);
  assert.match(text, /必须优先考虑的地点：外滩、上海博物馆/);
  assert.match(text, /固定安排：活动 \| 人民广场/);
  assert.match(text, /可用时间窗口：1 \| first day partial/);
  assert.match(text, /旅行节奏：平衡节奏/);
  assert.match(text, /主要交通偏好：metro/);
});

test("compiler confirmation is converted into labelled draft input before first-plan admission", () => {
  const text = buildPrePlanDraftTextFromCompilerIntent({
    destination: "杭州",
    trip_days: 2,
    pace: "relaxed",
    must_visit_places: [{ name: "西湖" }],
    optional_places: [{ name: "龙井村" }],
    fixed_events: [{ name: "中国茶叶博物馆", day: 1, start_time: "14:00", end_time: "16:00" }],
    preferences: [{ value: "本地小吃" }],
    constraints: [{ kind: "departure", value: "第 2 天 18:00 前需要结束行程" }],
    travel_mode: "rail",
  });

  assert.match(text, /城市：杭州/);
  assert.match(text, /行程天数：2 天/);
  assert.match(text, /景点：西湖、龙井村/);
  assert.match(text, /固定安排：1 14:00-16:00 中国茶叶博物馆/);
  assert.match(text, /偏好：本地小吃/);
  assert.match(text, /离开锚点：第 2 天 18:00 前需要结束行程/);
});

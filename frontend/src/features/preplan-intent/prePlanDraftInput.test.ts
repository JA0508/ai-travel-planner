import assert from "node:assert/strict";
import test from "node:test";
import { buildPrePlanDraftText } from "./prePlanDraftInput";

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

import assert from "node:assert/strict";
import test from "node:test";

import { buildRoadbookAdjustmentIndex } from "./roadbookAdjustmentIndexModel";
import type { DayLoad, RoutePreviewItem } from "./routePreviewModel";

test("offers only deterministic local repairs for a rushed day and verified system stop", () => {
  const index = buildRoadbookAdjustmentIndex({
    canRepair: true,
    loads: [load(1, "balanced"), load(2, "rushed")],
    stops: [
      stop({ stable_id: "must", day: 1, name: "灵隐寺", source_type: "user_seed", source_label: "必去" }),
      stop({ stable_id: "auto", day: 1, name: "湖畔小馆" }),
      stop({ stable_id: "fixed", day: 1, name: "中国茶叶博物馆", source_type: "user_fixed", is_fixed: true }),
    ],
  });

  assert.deepEqual(index.actions, [
    { kind: "relax_day", day: 2, label: "查看第 2 天的放松方案" },
    { kind: "replace_stop", day: 1, stopId: "auto", label: "检查「湖畔小馆」能否安全替换" },
  ]);
  assert.equal(index.summary, "有 2 个可以安全检查的小调整。");
});

test("does not invent an adjustment when no supported local repair exists", () => {
  const index = buildRoadbookAdjustmentIndex({
    canRepair: false,
    loads: [load(1, "rushed")],
    stops: [stop({ stable_id: "must", day: 1, name: "灵隐寺", source_type: "user_seed", source_label: "必去" })],
  });

  assert.deepEqual(index.actions, []);
  assert.equal(index.summary, "当前没有可安全自动微调的地方。");
});

function load(day: number, pace: DayLoad["pace"]): DayLoad {
  return {
    day,
    activityCount: 3,
    fixedCount: 0,
    activityMinutes: 180,
    travelMinutes: 30,
    routeDistanceMeters: 2000,
    pace,
    paceLabel: pace === "rushed" ? "偏赶" : "适中",
    explanation: "路线说明",
  };
}

function stop(overrides: Partial<RoutePreviewItem> = {}): RoutePreviewItem {
  return {
    stable_id: "auto",
    name: "湖畔小馆",
    type: "restaurant",
    start_time: "12:00",
    end_time: "13:00",
    is_fixed: false,
    source_type: "auto_seeded_meal",
    canonical_place_id: "amap:lake-side",
    verified_place: {
      stable_id: "amap:lake-side",
      original_name: "湖畔小馆",
      canonical_name: "湖畔小馆",
      provider: "amap",
      provider_place_id: "lake-side",
      latitude: 30.2,
      longitude: 120.1,
    },
    ...overrides,
  };
}

import assert from "node:assert/strict";
import test from "node:test";

import {
  buildRepairPreviewModel,
  latestRouteReloadActionLabel,
  latestRouteReloadReceipt,
  repairFailureMessage,
  undoRevisionReceipt,
  type LocalRepairImpact,
} from "./repairPreviewModel";
import type {
  RoutePreviewItinerary,
  RoutePreviewItem,
} from "./routePreviewModel";

const impact: LocalRepairImpact = {
  action: "move",
  stop_name: "龙井村茶歇",
  from_day: 1,
  to_day: 2,
  ownership: "system_suggested",
  protected: {
    fixed_mutations: 0,
    must_moves: 0,
    must_deletions: 0,
    full_planner_calls: 0,
  },
};

test("builds a traveler-facing move from authoritative before and after snapshots", () => {
  const before = itinerary({ dayOneTravelMinutes: 80, dayTwoTravelMinutes: 20 });
  const after = itinerary({
    dayOneTravelMinutes: 50,
    dayTwoTravelMinutes: 35,
    moveSuggestionToDayTwo: true,
  });

  const model = buildRepairPreviewModel(before, after, 1, impact);

  assert.deepEqual(model.affectedDays, [1, 2]);
  assert.deepEqual(model.change, {
    action: "move",
    stopName: "龙井村茶歇",
    fromDay: 1,
    toDay: 2,
  });
  assert.equal(model.beforeSections[0].items.some((item) => item.name === "龙井村茶歇"), true);
  assert.equal(model.afterSections[0].items.some((item) => item.name === "龙井村茶歇"), false);
  assert.equal(model.afterSections[1].items.some((item) => item.name === "龙井村茶歇"), true);
  assert.equal(model.quantitativeImpact.activityDelta, 1);
  assert.equal(model.quantitativeImpact.travelMinutesSaved, 30);
});

test("only calls fixed and must-visit items protected when snapshots prove they are unchanged", () => {
  const before = itinerary({ dayOneTravelMinutes: 80, dayTwoTravelMinutes: 20 });
  const after = itinerary({
    dayOneTravelMinutes: 50,
    dayTwoTravelMinutes: 35,
    moveSuggestionToDayTwo: true,
  });

  const model = buildRepairPreviewModel(before, after, 1, impact);

  assert.deepEqual(
    model.protectedItems.map((item) => [item.name, item.reason]),
    [
      ["灵隐寺", "你明确说想去"],
      ["中国茶叶博物馆", "已经留好的时间，不会被移动"],
    ],
  );

  const changedFixed = structuredClone(after);
  changedFixed.days[1].blocks[0].items[0].start_time = "15:00";
  assert.deepEqual(
    buildRepairPreviewModel(before, changedFixed, 1, impact).protectedItems.map((item) => item.name),
    ["灵隐寺"],
  );
});

test("uses the proposal stop id when a day contains duplicate place names", () => {
  const before = itinerary({ dayOneTravelMinutes: 80, dayTwoTravelMinutes: 20 });
  const after = itinerary({
    dayOneTravelMinutes: 50,
    dayTwoTravelMinutes: 35,
    moveSuggestionToDayTwo: true,
  });
  const duplicate = item({
    stable_id: "suggestion-tea-duplicate",
    name: "龙井村茶歇",
    start_time: "11:30",
    end_time: "12:15",
    source_type: "auto_filled",
    source_label: "系统补充",
  });
  before.days[0].blocks[0].items.splice(1, 0, duplicate);
  after.days[0].blocks[0].items.push(duplicate);

  const model = buildRepairPreviewModel(before, after, 1, {
    ...impact,
    stop_id: "suggestion-tea",
  });
  const changed = [...model.beforeSections, ...model.afterSections]
    .flatMap((section) => section.items)
    .filter((entry) => entry.changed);

  assert.equal(changed.length, 2);
  assert.equal(changed.every((entry) => entry.id === "suggestion-tea"), true);
  assert.equal(
    model.afterSections[0].items.some((entry) => entry.id === "suggestion-tea-duplicate"),
    true,
  );
});

test("does not fabricate saved minutes when server load evidence is missing", () => {
  const before = itinerary({ dayOneTravelMinutes: 80, dayTwoTravelMinutes: 20 });
  const after = itinerary({
    dayOneTravelMinutes: 50,
    dayTwoTravelMinutes: 35,
    moveSuggestionToDayTwo: true,
  });
  after.planner_realism = null;

  const model = buildRepairPreviewModel(before, after, 1, impact);

  assert.equal(model.quantitativeImpact.travelMinutesSaved, null);
  assert.equal(model.quantitativeImpact.activityDelta, null);
});

test("translates stale and failed operations without exposing protocol codes", () => {
  const stale = repairFailureMessage("stale_mutation_proposal", "apply");
  const staleUndo = repairFailureMessage("undo_target_not_current", "undo");
  const failed = repairFailureMessage(undefined, "apply");

  assert.equal(stale, "路线刚刚发生了变化。这次调整没有保存，原路线保持不变。请基于最新版本重新看看调整建议。");
  assert.equal(staleUndo, "路线刚刚发生了变化。这次撤销没有保存。请载入最新路线确认当前安排。");
  assert.equal(failed, "这次调整没有保存。你的原路线仍然保持不变。");
  assert.doesNotMatch(`${stale}${staleUndo}${failed}`, /409|422|stale_|proposal_|undo_target/);
});

test("names the compensating revision after a persisted local undo", () => {
  assert.equal(
    undoRevisionReceipt("relax_day", 4),
    "已撤销这次调整，并保存为新版本 4。调整前的路线已恢复。",
  );
  assert.equal(
    undoRevisionReceipt("replace_stop", 7),
    "已撤销这次替换，并保存为新版本 7。原来的地点和相邻路线已恢复。",
  );
});

test("explains the safe next step after loading a newer route", () => {
  assert.equal(
    latestRouteReloadReceipt("relax_day", 4),
    "已载入最新保存版本 4；没有应用刚才的调整。请基于这版路线重新查看当天是否仍然太赶。",
  );
  assert.equal(
    latestRouteReloadReceipt("replace_stop", 7),
    "已载入最新保存版本 7；没有应用刚才的替换。请基于这版路线重新选择地点。",
  );
});

test("distinguishes the first latest-route load from a recoverable retry", () => {
  assert.equal(latestRouteReloadActionLabel(false), "载入最新路线");
  assert.equal(latestRouteReloadActionLabel(true), "重新载入最新路线");
});

test("does not describe an unknown repair owner as a system suggestion", () => {
  const before = itinerary({ dayOneTravelMinutes: 80, dayTwoTravelMinutes: 20 });
  const after = itinerary({
    dayOneTravelMinutes: 50,
    dayTwoTravelMinutes: 35,
    moveSuggestionToDayTwo: true,
  });

  const model = buildRepairPreviewModel(before, after, 1, {
    ...impact,
    ownership: "user_adjustable",
  });

  assert.doesNotMatch(model.reason, /系统补充/);
  assert.match(model.reason, /可调整/);
});

function itinerary({
  dayOneTravelMinutes,
  dayTwoTravelMinutes,
  moveSuggestionToDayTwo = false,
}: {
  dayOneTravelMinutes: number;
  dayTwoTravelMinutes: number;
  moveSuggestionToDayTwo?: boolean;
}): RoutePreviewItinerary {
  const must = item({
    stable_id: "must-lingyin",
    name: "灵隐寺",
    start_time: "09:00",
    end_time: "10:30",
    source_type: "user_seed",
    source_label: "必去",
  });
  const suggestion = item({
    stable_id: "suggestion-tea",
    name: "龙井村茶歇",
    start_time: moveSuggestionToDayTwo ? "16:00" : "13:00",
    end_time: moveSuggestionToDayTwo ? "17:00" : "14:00",
    source_type: "auto_filled",
    source_label: "系统补充",
  });
  const fixed = item({
    stable_id: "fixed-museum",
    name: "中国茶叶博物馆",
    start_time: "14:00",
    end_time: "16:00",
    source_type: "user_fixed",
    is_fixed: true,
  });
  return {
    trip_days: 2,
    days: [
      {
        day: 1,
        blocks: [{
          block_type: "morning",
          start_time: "09:00",
          end_time: "18:00",
          items: moveSuggestionToDayTwo ? [must] : [must, suggestion],
        }],
      },
      {
        day: 2,
        blocks: [{
          block_type: "afternoon",
          start_time: "13:00",
          end_time: "18:00",
          items: moveSuggestionToDayTwo ? [fixed, suggestion] : [fixed],
        }],
      },
    ],
    planner_realism: {
      daily_loads: [
        {
          day: 1,
          classification: moveSuggestionToDayTwo ? "balanced" : "rushed",
          activity_count: moveSuggestionToDayTwo ? 1 : 2,
          fixed_count: 0,
          activity_minutes: moveSuggestionToDayTwo ? 90 : 150,
          travel_minutes: dayOneTravelMinutes,
          route_distance_m: 2400,
          reason_codes: [],
          explanation: "服务端负载判定",
        },
        {
          day: 2,
          classification: "balanced",
          activity_count: moveSuggestionToDayTwo ? 2 : 1,
          fixed_count: 1,
          activity_minutes: moveSuggestionToDayTwo ? 180 : 120,
          travel_minutes: dayTwoTravelMinutes,
          route_distance_m: 1800,
          reason_codes: [],
          explanation: "服务端负载判定",
        },
      ],
    },
  };
}

function item(overrides: Partial<RoutePreviewItem>): RoutePreviewItem {
  return {
    stable_id: "item",
    name: "地点",
    type: "scenic",
    city: "杭州",
    latitude: 30.2,
    longitude: 120.1,
    start_time: "09:00",
    end_time: "10:00",
    duration_minutes: 60,
    is_fixed: false,
    travel_data_status: "confirmed",
    travel_duration_s: 840,
    travel_distance_m: 1100,
    ...overrides,
  };
}

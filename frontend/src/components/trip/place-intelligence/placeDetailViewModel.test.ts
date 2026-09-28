import { strict as assert } from "node:assert";
import { test } from "node:test";
import {
  buildNeighborStopIds,
  buildPlaceDetailViewModel,
  buildRelatedRouteSegmentKeys,
  buildSpatialReasoning,
} from "./placeDetailViewModel";
import type {
  EditableRouteDay,
  EditableRouteStop,
  POIDetailPreview,
  RoutePreviewMap,
  ScheduledItemLike,
  TimelineBlockType,
} from "../MobileEditRouteWorkspace";

test("builds a reasonable fit with provider facts and deterministic route evidence", () => {
  const days = makeDays();
  const stop = days[0].stops[1];
  const model = buildPlaceDetailViewModel({
    stop,
    allDays: days,
    originLabel: "杭州东站",
    routePreviewMap: routeMap(days),
    routeMode: "walk",
    poiDetail: poiDetail(stop.item.name),
    poiDetailState: "idle",
  });

  assert.equal(model.trust.verdict, "reasonable-fit");
  assert.equal(model.routeFit.topology, "linear");
  assert.equal(model.routeFit.previousStop?.name, "西湖断桥");
  assert.equal(model.routeFit.nextStop?.name, "湖滨银泰晚餐");
  assert.ok(model.evidence.some((item) => item.kind === "provider-fact" && item.key === "provider-address"));
  assert.deepEqual(
    model.evidence.find((item) => item.key === "provider-opening-hours"),
    {
      key: "provider-opening-hours",
      kind: "provider-fact",
      label: "营业时间快照",
      detail: "09:00-17:00 · 地点详情服务 · 查询于 2026-09-26T12:00:00Z",
    },
  );
  assert.ok(model.evidence.some((item) => item.kind === "deterministic-inference" && item.key === "neighbor-order"));
  assert.deepEqual(buildNeighborStopIds(stop, days), [days[0].stops[0].id, days[0].stops[2].id]);
  assert.deepEqual(buildRelatedRouteSegmentKeys(stop, days), [
    `${days[0].stops[0].id}->${stop.id}`,
    `${stop.id}->${days[0].stops[2].id}`,
  ]);
});

test("keeps an unsuccessful provider lookup timestamp without treating it as a POI fact", () => {
  const days = makeDays();
  const stop = days[0].stops[1];
  const model = buildPlaceDetailViewModel({
    stop,
    allDays: days,
    originLabel: "杭州东站",
    routePreviewMap: routeMap(days),
    routeMode: "walk",
    poiDetail: null,
    poiDetailState: "failed",
    poiDetailObservedAt: "2026-09-26T12:00:00Z",
  });

  assert.equal(model.identity.observedAt, "2026-09-26T12:00:00Z");
  assert.equal(model.trust.verdict, "uncertain-fit");
  assert.ok(model.evidence.some((item) => item.key === "missing-poi-detail"));
  assert.equal(model.evidence.some((item) => item.key === "provider-address"), false);
});

test("labels deterministic daily-hours coverage without claiming date or booking verification", () => {
  const days = makeDays();
  const stop = days[0].stops[1];
  const model = buildPlaceDetailViewModel({
    stop,
    allDays: days,
    originLabel: "杭州东站",
    routePreviewMap: routeMap(days),
    routeMode: "walk",
    poiDetail: { ...poiDetail(stop.item.name), open_time_coverage: "covers_scheduled_window" },
    poiDetailState: "idle",
  });

  assert.deepEqual(
    model.evidence.find((item) => item.key === "provider-opening-hours-coverage"),
    {
      key: "provider-opening-hours-coverage",
      kind: "deterministic-inference",
      label: "常规时段比对",
      detail: "提供方的单段日常营业时间覆盖当前安排钟点；具体日期、临时闭馆和预约规则仍待核验。",
    },
  );
});

test("protects fixed events as user constraints and disables destructive actions", () => {
  const days = makeDays();
  const stop = days[0].stops[0];
  const model = buildPlaceDetailViewModel({
    stop,
    allDays: days,
    originLabel: "杭州东站",
    routePreviewMap: routeMap(days),
    routeMode: "walk",
    poiDetail: poiDetail(stop.item.name),
    poiDetailState: "idle",
  });

  assert.equal(model.trust.verdict, "strong-fit");
  assert.equal(model.visitContext.role, "fixed-event");
  assert.equal(model.actions.canRemove, false);
  assert.equal(model.actions.canMoveToUnplanned, false);
  assert.ok(model.caveats.some((item) => item.key === "fixed-event-boundary"));
  assert.ok(model.evidence.some((item) => item.kind === "user-constraint"));
});

test("labels auto-filled stops as completion suggestions", () => {
  const days = makeDays();
  const stop = days[0].stops[1];
  const model = buildPlaceDetailViewModel({
    stop,
    allDays: days,
    originLabel: "杭州东站",
    routePreviewMap: routeMap(days),
    routeMode: "walk",
    poiDetail: poiDetail(stop.item.name),
    poiDetailState: "idle",
  });

  assert.equal(model.visitContext.role, "completion-suggestion");
  assert.match(model.visitContext.reason ?? "", /补全/);
});

test("surfaces route pressure as heuristic review without calling it provider evidence", () => {
  const days = makeDays();
  const stop = days[0].stops[1];
  const riskyRouteMap = routeMap(days, { inboundSeconds: 5400 });
  const model = buildPlaceDetailViewModel({
    stop,
    allDays: days,
    originLabel: "杭州东站",
    routePreviewMap: riskyRouteMap,
    routeMode: "drive",
    poiDetail: poiDetail(stop.item.name),
    poiDetailState: "idle",
  });

  assert.equal(model.trust.verdict, "needs-review");
  assert.equal(model.routeFit.topology, "minor-detour");
  assert.ok(model.routeFit.observations.some((item) => item.kind === "heuristic"));
  assert.ok(!model.evidence.some((item) => item.kind === "heuristic"));
  assert.notEqual(model.routeFit.spatialSummary, "backtracking");
});

test("degrades to missing-data caveats when adjacent route data is absent", () => {
  const days = makeDays();
  const stop = days[0].stops[1];
  stop.item.travel_from_name = "未知起点";
  days[0].stops[2].item.travel_from_name = "未知起点";
  const model = buildPlaceDetailViewModel({
    stop,
    allDays: days,
    originLabel: "杭州东站",
    routePreviewMap: {},
    routeMode: "walk",
    poiDetail: poiDetail(stop.item.name),
    poiDetailState: "idle",
  });

  assert.equal(model.trust.verdict, "uncertain-fit");
  assert.equal(model.routeFit.topology, "unknown");
  assert.ok(model.caveats.some((item) => item.key === "missing-inbound-route"));
  assert.ok(model.caveats.some((item) => item.key === "missing-outbound-route"));
});

test("keeps first and last stops explainable without inventing neighbors", () => {
  const days = makeDays();
  const first = days[0].stops[0];
  const last = days[0].stops[2];

  const firstModel = buildPlaceDetailViewModel({
    stop: first,
    allDays: days,
    originLabel: "杭州东站",
    routePreviewMap: routeMap(days),
    routeMode: "walk",
    poiDetail: poiDetail(first.item.name),
    poiDetailState: "idle",
  });
  const lastModel = buildPlaceDetailViewModel({
    stop: last,
    allDays: days,
    originLabel: "杭州东站",
    routePreviewMap: routeMap(days),
    routeMode: "walk",
    poiDetail: poiDetail(last.item.name),
    poiDetailState: "idle",
  });

  assert.equal(firstModel.routeFit.previousStop, undefined);
  assert.equal(firstModel.routeFit.nextStop?.name, "浙江省博物馆");
  assert.equal(lastModel.routeFit.previousStop?.name, "浙江省博物馆");
  assert.equal(lastModel.routeFit.nextStop, undefined);
});

test("records missing provider detail separately from spatial route logic", () => {
  const days = makeDays();
  const stop = days[0].stops[1];
  const model = buildPlaceDetailViewModel({
    stop,
    allDays: days,
    originLabel: "杭州东站",
    routePreviewMap: routeMap(days),
    routeMode: "walk",
    poiDetail: null,
    poiDetailState: "failed",
  });

  assert.equal(model.trust.verdict, "uncertain-fit");
  assert.ok(model.evidence.some((item) => item.kind === "missing-data" && item.key === "missing-poi-detail"));
  assert.equal(model.routeFit.topology, "linear");
});

test("marks missing coordinates as unknown spatial topology", () => {
  const days = makeDays({ removeCurrentCoordinates: true });
  const stop = days[0].stops[1];
  const spatial = buildSpatialReasoning({
    stop,
    previousStop: days[0].stops[0],
    nextStop: days[0].stops[2],
    originLabel: "杭州东站",
    routePreviewMap: routeMap(days),
    routeMode: "walk",
  });

  assert.equal(spatial.topology, "unknown");
  assert.ok(spatial.caveats.some((item) => item.key === "missing-current-coordinates"));
});

function makeDays(options: { removeCurrentCoordinates?: boolean } = {}): EditableRouteDay[] {
  const westLake = makeStop({
    id: "1-morning-西湖断桥-09:00:00-10:30:00-0",
    name: "西湖断桥",
    blockType: "morning",
    latitude: 30.2588,
    longitude: 120.1475,
    isFixed: true,
    sourceType: "user_fixed",
    travelFromName: "杭州东站",
    travelDurationSeconds: 1380,
  });
  const museum = makeStop({
    id: "1-afternoon-浙江省博物馆-11:00:00-13:00:00-0",
    name: "浙江省博物馆",
    blockType: "afternoon",
    latitude: options.removeCurrentCoordinates ? null : 30.2521,
    longitude: options.removeCurrentCoordinates ? null : 120.1434,
    sourceType: "auto_filled",
    sourceReason: "用于补全西湖文化路线。",
    travelFromName: "西湖断桥",
    travelDurationSeconds: 900,
  });
  const dinner = makeStop({
    id: "1-evening-湖滨银泰晚餐-18:00:00-19:30:00-0",
    name: "湖滨银泰晚餐",
    blockType: "evening",
    type: "restaurant",
    latitude: 30.256,
    longitude: 120.1666,
    sourceType: "auto_seeded_meal",
    travelFromName: "浙江省博物馆",
    travelDurationSeconds: 1020,
  });
  return [{
    day: 1,
    label: "Day 1",
    originalStopCount: 3,
    stops: [westLake, museum, dinner],
  }];
}

function routeMap(days: EditableRouteDay[], options: { inboundSeconds?: number } = {}): RoutePreviewMap {
  const [first, second, third] = days[0].stops;
  return {
    [`${first.id}->${second.id}`]: segment(`${first.id}->${second.id}`, first, second, options.inboundSeconds ?? 900),
    [`${second.id}->${third.id}`]: segment(`${second.id}->${third.id}`, second, third, 1020),
  };
}

function segment(key: string, from: EditableRouteStop, to: EditableRouteStop, durationSeconds: number) {
  return {
    segment_key: key,
    from_name: from.item.name,
    to_name: to.item.name,
    distance_m: durationSeconds >= 3000 ? 22000 : 1800,
    duration_s: durationSeconds,
    source: "fixture_provider",
    mode: "walk" as const,
    path_points: [
      { latitude: from.item.latitude ?? 0, longitude: from.item.longitude ?? 0 },
      { latitude: to.item.latitude ?? 0, longitude: to.item.longitude ?? 0 },
    ],
  };
}

function makeStop({
  id,
  name,
  blockType,
  type = "scenic",
  latitude,
  longitude,
  isFixed = false,
  sourceType = "user_seed",
  sourceReason = "用户明确提到。",
  travelFromName,
  travelDurationSeconds,
}: {
  id: string;
  name: string;
  blockType: TimelineBlockType;
  type?: ScheduledItemLike["type"];
  latitude: number | null;
  longitude: number | null;
  isFixed?: boolean;
  sourceType?: NonNullable<ScheduledItemLike["source_type"]>;
  sourceReason?: string;
  travelFromName: string;
  travelDurationSeconds: number;
}): EditableRouteStop {
  const startEnd = blockType === "morning" ? ["09:00:00", "10:30:00"] : blockType === "afternoon" ? ["11:00:00", "13:00:00"] : ["18:00:00", "19:30:00"];
  return {
    id,
    day: 1,
    originalDay: 1,
    originalIndex: 0,
    originalIsFixed: isFixed,
    blockType,
    originalBlockType: blockType,
    item: {
      name,
      type,
      latitude,
      longitude,
      start_time: startEnd[0],
      end_time: startEnd[1],
      is_fixed: isFixed,
      placement_reason: "根据当天空间顺序放入路线。",
      source_type: sourceType,
      source_label: sourceType === "auto_filled" ? "补全地点" : "用户地点",
      source_reason: sourceReason,
      travel_from_name: travelFromName,
      travel_distance_m: 1800,
      travel_duration_s: travelDurationSeconds,
    },
  };
}

function poiDetail(name: string): POIDetailPreview {
  return {
    found: true,
    name,
    address: `${name} 示例地址`,
    category: "风景名胜",
    business_area: "西湖",
    rating: null,
    cost: null,
    tel: null,
    website: null,
    open_time: "09:00-17:00",
    photo_url: null,
    latitude: 30.25,
    longitude: 120.14,
    source: "fixture",
    observed_at: "2026-09-26T12:00:00Z",
    failure_reason: null,
  };
}

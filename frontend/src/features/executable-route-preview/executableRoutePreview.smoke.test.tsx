import assert from "node:assert/strict";
import test from "node:test";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import React from "react";
import { PlaceDetailPanel } from "@/components/trip/place-intelligence/PlaceDetailPanel";
import { renderToStaticMarkup } from "react-dom/server";
import {
  ExecutableRoutePreview,
  focusRoadbookRelaxDayAfterRepairDismissal,
  focusRoadbookStopAfterReplacementDismissal,
} from "./ExecutableRoutePreview";
import { buildRoadbookAdjustmentGuide } from "./SavedLivingRoadbook";
import type { RoutePreviewItinerary } from "./routePreviewModel";
import type { PlaceDetailViewModel } from "@/components/trip/place-intelligence/placeDetailViewModel";

const componentPath = fileURLToPath(new URL("./ExecutableRoutePreview.tsx", import.meta.url));
const savedRoadbookPath = fileURLToPath(new URL("./SavedLivingRoadbook.tsx", import.meta.url));
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

test("draft route preview can keep its explicit save action beside the preview", () => {
  const html = renderToStaticMarkup(
    <ExecutableRoutePreview
      itinerary={itinerary}
      variant="draft"
      draftConfirmation={{
        label: "确认并生成行程",
        hint: "确认后才会保存为正式行程。",
        disabled: false,
        onConfirm: () => undefined,
      }}
    />,
  );

  assert.match(html, /确认并生成行程/);
  assert.match(html, /data-draft-route-confirmation="true"/);
});

test("draft route preview keeps a recoverable save failure beside its confirmation action", () => {
  const html = renderToStaticMarkup(
    <ExecutableRoutePreview
      itinerary={itinerary}
      variant="draft"
      draftConfirmation={{
        label: "重新保存正式行程",
        hint: "确认后才会保存为正式行程。",
        recoveryMessage: "暂时无法保存正式行程，路线预览仍在这里。",
        disabled: false,
        onConfirm: () => undefined,
      }}
    />,
  );

  assert.match(html, /role="alert"/);
  assert.match(html, /暂时无法保存正式行程，路线预览仍在这里。/);
  assert.match(html, /重新保存正式行程/);
});

test("saved route uses an on-the-road workspace vocabulary", () => {
  const saved = structuredClone(itinerary);
  saved.days[0].blocks[0].items[0].is_fixed = true;
  saved.days[0].blocks[0].items[0].placement_reason = "Reused canonical coordinates from the intent handoff.";
  const html = renderToStaticMarkup(<ExecutableRoutePreview itinerary={saved} variant="saved" tripId="trip-1" baseRevisionId="revision-1" onApplied={() => undefined} />);
  assert.match(html, /这份行程已保存为正式路线/);
  assert.match(html, /role="status"/);
  assert.match(html, /已保存为正式路线。可继续查看路线。/);
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

test("saved roadbook surfaces a route-verification count before a traveler scans the timeline", () => {
  const saved = structuredClone(itinerary);
  saved.days[0].blocks[0].items[0] = {
    ...saved.days[0].blocks[0].items[0],
    travel_duration_s: null,
    travel_distance_m: null,
    travel_data_status: "unavailable",
  };

  const html = renderToStaticMarkup(<ExecutableRoutePreview itinerary={saved} variant="saved" tripId="trip-1" baseRevisionId="revision-1" onApplied={() => undefined} />);

  assert.match(html, /有 1 段相邻路线待确认/);
  assert.match(html, /不会按零分钟处理，请在出发前核验。/);
});

test("saved roadbook does not present its internal route center as a confirmed leg", () => {
  const saved = structuredClone(itinerary);
  saved.planning_anchor_source = {
    source_type: "route_centroid",
    source_name: "西湖附近路线中心",
  };
  saved.days[0].blocks[0].items[0] = {
    ...saved.days[0].blocks[0].items[0],
    travel_from_name: "西湖附近路线中心",
    travel_duration_s: 0,
    travel_distance_m: 1,
  };

  const html = renderToStaticMarkup(<ExecutableRoutePreview itinerary={saved} variant="saved" tripId="trip-1" baseRevisionId="revision-1" onApplied={() => undefined} />);

  assert.doesNotMatch(html, /西湖附近路线中心/);
  assert.doesNotMatch(html, /0 分钟 · 1 米/);
});

test("saved roadbook gives first-time readers a live route-reading guide", () => {
  const html = renderToStaticMarkup(
    <ExecutableRoutePreview
      itinerary={itinerary}
      variant="saved"
      tripId="trip-1"
      baseRevisionId="revision-1"
      onApplied={() => undefined}
    />,
  );

  assert.match(html, /aria-label="阅读路线提示"/);
  assert.match(html, /正在查看第 1 天/);
  assert.match(html, /点击时间线中的地点，即可切换当前地点；地图区域会同步显示可用的路线信息。/);
  assert.match(html, /当前没有需要调整的项目；已明确的安排会按原计划保留。/);
});

test("roadbook place detail labels missing operational facts as pending verification", () => {
  const viewModel: PlaceDetailViewModel = {
    identity: { id: "west-lake", name: "西湖", category: "景点", observedAt: "2026-09-26T12:00:00Z" },
    schedule: { dayIndex: 1, blockLabel: "上午", startTime: "09:00", endTime: "11:00", durationLabel: "2 小时" },
    trust: {
      verdict: "uncertain-fit",
      label: "Uncertain fit",
      headline: "位置关系可读，但事实证据不足",
      explanation: "当前缺少 provider 地点详情或完整路线段，不应把启发式判断当作事实。",
    },
    routeFit: { topology: "unknown", spatialSummary: "相邻路线待确认", observations: [] },
    visitContext: { role: "anchor", label: "行程地点" },
    evidence: [],
    caveats: [{ key: "missing-open-time", kind: "missing-data", label: "营业时间待验证", detail: "当前无法确认该地点是否覆盖安排时间。" }],
    actions: { canKeep: true, canReplace: false, canRemove: false, canMoveToUnplanned: false },
  };

  const reactGlobal = globalThis as typeof globalThis & { React?: typeof React };
  const originalReact = reactGlobal.React;
  reactGlobal.React = React;
  try {
    const html = renderToStaticMarkup(<PlaceDetailPanel viewModel={viewModel} onBack={() => undefined} appearance="roadbook" />);

    assert.match(html, /核验状态/);
    assert.match(html, /地点详情查询于/);
    assert.match(html, /地点详情（如营业时间）待验证；当前安排只是时间骨架，不能确认该地点在此时开放。/);
    assert.doesNotMatch(html, /地点详情与相邻路线已有可用证据/);
  } finally {
    reactGlobal.React = originalReact;
  }
});

test("roadbook shows a provider opening-hour snapshot without treating it as booking proof", () => {
  const viewModel: PlaceDetailViewModel = {
    identity: { id: "west-lake", name: "西湖", category: "景点", observedAt: "2026-09-26T12:00:00Z" },
    schedule: { dayIndex: 1, blockLabel: "上午", startTime: "09:00", endTime: "11:00", durationLabel: "2 小时" },
    trust: {
      verdict: "reasonable-fit",
      label: "Reasonable fit",
      headline: "这个地点与前后路线衔接合理",
      explanation: "相邻路线可用。",
    },
    routeFit: { topology: "linear", spatialSummary: "相邻路线顺路", observations: [] },
    visitContext: { role: "anchor", label: "行程地点" },
    evidence: [{
      key: "provider-opening-hours",
      kind: "provider-fact",
      label: "营业时间快照",
      detail: "09:00-17:00 · 地点详情服务 · 查询于 2026-09-26T12:00:00Z",
    }],
    caveats: [],
    actions: { canKeep: true, canReplace: false, canRemove: false, canMoveToUnplanned: false },
  };

  const reactGlobal = globalThis as typeof globalThis & { React?: typeof React };
  const originalReact = reactGlobal.React;
  reactGlobal.React = React;
  try {
    const html = renderToStaticMarkup(<PlaceDetailPanel viewModel={viewModel} onBack={() => undefined} appearance="roadbook" />);

    assert.match(html, /营业时间快照/);
    assert.match(html, /09:00-17:00/);
    assert.match(html, /这是地点详情查询快照/);
    assert.match(html, /不代表已完成预约/);
  } finally {
    reactGlobal.React = originalReact;
  }
});

test("roadbook promotes a deterministic opening-hours conflict as the departure note", () => {
  const viewModel: PlaceDetailViewModel = {
    identity: { id: "west-lake", name: "西湖", category: "景点", observedAt: "2026-09-26T12:00:00Z" },
    schedule: { dayIndex: 1, blockLabel: "晚上", startTime: "18:00", endTime: "20:00", durationLabel: "2 小时" },
    trust: {
      verdict: "needs-review",
      label: "Needs review",
      headline: "当前安排落在日常营业时段之外",
      explanation: "提供方的单段日常营业时间不覆盖当前钟点。",
    },
    routeFit: { topology: "linear", spatialSummary: "相邻路线顺路", observations: [] },
    visitContext: { role: "anchor", label: "行程地点" },
    evidence: [{
      key: "provider-opening-hours",
      kind: "provider-fact",
      label: "营业时间快照",
      detail: "09:00-17:00 · 地点详情服务 · 查询于 2026-09-26T12:00:00Z",
    }, {
      key: "provider-opening-hours-coverage",
      kind: "deterministic-inference",
      label: "常规时段比对",
      detail: "提供方的单段日常营业时间不覆盖当前安排钟点；请调整这一站或在出发前核验具体日期规则。",
    }],
    caveats: [{
      key: "opening-hours-conflict",
      kind: "deterministic-inference",
      label: "安排时段冲突",
      detail: "提供方的单段日常营业时间不覆盖当前安排钟点；请先核验具体日期规则，再决定是否局部调整。",
    }],
    actions: { canKeep: true, canReplace: false, canRemove: false, canMoveToUnplanned: false },
  };

  const reactGlobal = globalThis as typeof globalThis & { React?: typeof React };
  const originalReact = reactGlobal.React;
  reactGlobal.React = React;
  try {
    const html = renderToStaticMarkup(<PlaceDetailPanel viewModel={viewModel} onBack={() => undefined} appearance="roadbook" />);

    assert.match(html, /出发前留意：提供方的单段日常营业时间不覆盖当前安排钟点/);
    assert.match(html, /具体日期规则/);
  } finally {
    reactGlobal.React = originalReact;
  }
});

test("roadbook distinguishes a protected fixed arrangement from a verified reservation", () => {
  const viewModel: PlaceDetailViewModel = {
    identity: { id: "museum", name: "中国茶叶博物馆", category: "景点" },
    schedule: { dayIndex: 2, blockLabel: "下午", startTime: "14:00", endTime: "16:00", durationLabel: "2 小时" },
    trust: {
      verdict: "strong-fit",
      label: "Strong route fit",
      headline: "这是受保护的行程边界",
      explanation: "固定安排会被保留。",
    },
    routeFit: { topology: "linear", spatialSummary: "相邻路线顺路", observations: [] },
    visitContext: { role: "fixed-event", label: "Fixed event" },
    evidence: [{
      key: "user-source",
      kind: "user-constraint",
      label: "来自用户输入",
      detail: "用户说明这是固定预约。",
    }],
    caveats: [{
      key: "fixed-event-boundary",
      kind: "user-constraint",
      label: "固定边界",
      detail: "这个地点不可被自动替换或移除。",
    }],
    actions: { canKeep: true, canReplace: false, canRemove: false, canMoveToUnplanned: false },
  };

  const reactGlobal = globalThis as typeof globalThis & { React?: typeof React };
  const originalReact = reactGlobal.React;
  reactGlobal.React = React;
  try {
    const html = renderToStaticMarkup(<PlaceDetailPanel viewModel={viewModel} onBack={() => undefined} appearance="roadbook" />);

    assert.match(html, /这个固定安排会按你的输入保护/);
    assert.match(html, /尚未核验订单、入场资格或预约状态/);
  } finally {
    reactGlobal.React = originalReact;
  }
});

test("roadbook place detail keeps missing facts pending when the route also needs review", () => {
  const viewModel: PlaceDetailViewModel = {
    identity: { id: "west-lake", name: "西湖", category: "景点" },
    schedule: { dayIndex: 1, blockLabel: "上午", startTime: "09:00", endTime: "11:00", durationLabel: "2 小时" },
    trust: {
      verdict: "needs-review",
      label: "Needs review",
      headline: "这个地点可能带来路线压力",
      explanation: "相邻移动成本需要复核。",
    },
    routeFit: { topology: "minor-detour", spatialSummary: "相邻路线需要复核", observations: [] },
    visitContext: { role: "anchor", label: "行程地点" },
    evidence: [],
    caveats: [
      { key: "route-pressure", kind: "heuristic", label: "路线压力", detail: "建议复核。" },
      { key: "missing-open-time", kind: "missing-data", label: "营业时间待验证", detail: "当前无法确认该地点是否覆盖安排时间。" },
    ],
    actions: { canKeep: true, canReplace: false, canRemove: false, canMoveToUnplanned: false },
  };
  const reactGlobal = globalThis as typeof globalThis & { React?: typeof React };
  const originalReact = reactGlobal.React;
  reactGlobal.React = React;
  try {
    const html = renderToStaticMarkup(<PlaceDetailPanel viewModel={viewModel} onBack={() => undefined} appearance="roadbook" />);

    assert.match(html, /地点详情（如营业时间）待验证；当前安排只是时间骨架，不能确认该地点在此时开放。/);
    assert.doesNotMatch(html, /地点详情可用；相邻路线仍建议复核/);
  } finally {
    reactGlobal.React = originalReact;
  }
});

test("saved roadbook describes only adjustment paths that are currently available", () => {
  assert.equal(
    buildRoadbookAdjustmentGuide({ hasSafeReplacement: false, hasRelaxableDay: false }),
    "当前没有需要调整的项目；已明确的安排会按原计划保留。",
  );
  assert.equal(
    buildRoadbookAdjustmentGuide({ hasSafeReplacement: true, hasRelaxableDay: false }),
    "如需调整：可先检查一站是否有安全替换。",
  );
  assert.equal(
    buildRoadbookAdjustmentGuide({ hasSafeReplacement: false, hasRelaxableDay: true }),
    "如需调整：可请求放松偏紧的一天；已经留好的时间不会移动。",
  );
  assert.equal(
    buildRoadbookAdjustmentGuide({ hasSafeReplacement: true, hasRelaxableDay: true }),
    "如需调整：可检查一站的安全替换，或放松偏紧的一天。",
  );
});

test("dismissing replacement exploration restores focus to the original route stop", () => {
  const originalDocument = Object.getOwnPropertyDescriptor(globalThis, "document");
  let selector = "";
  let focused = false;
  Object.defineProperty(globalThis, "document", {
    configurable: true,
    value: {
      querySelector(value: string) {
        selector = value;
        return { focus: () => { focused = true; } };
      },
    },
  });

  try {
    focusRoadbookStopAfterReplacementDismissal('stop "quoted" \\ slash');
    assert.equal(selector, '[data-route-stop-id="stop \\"quoted\\" \\\\ slash"]');
    assert.equal(focused, true);
  } finally {
    if (originalDocument) {
      Object.defineProperty(globalThis, "document", originalDocument);
    } else {
      Reflect.deleteProperty(globalThis, "document");
    }
  }
});

test("dismissing a route relaxation preview restores focus to that day's repair control", () => {
  const originalDocument = Object.getOwnPropertyDescriptor(globalThis, "document");
  let selector = "";
  let focused = false;
  Object.defineProperty(globalThis, "document", {
    configurable: true,
    value: {
      querySelector(value: string) {
        selector = value;
        return { focus: () => { focused = true; } };
      },
    },
  });

  try {
    focusRoadbookRelaxDayAfterRepairDismissal(2);
    assert.equal(selector, '[data-roadbook-relax-day="2"]');
    assert.equal(focused, true);
  } finally {
    if (originalDocument) Object.defineProperty(globalThis, "document", originalDocument);
    else Reflect.deleteProperty(globalThis, "document");
  }
});

test("saved route offers local repair only for a rushed day", () => {
  const rushed = structuredClone(itinerary);
  const dailyLoads = rushed.planner_realism?.daily_loads;
  assert.ok(dailyLoads?.[0]);
  dailyLoads[0].classification = "rushed";
  const html = renderToStaticMarkup(<ExecutableRoutePreview itinerary={rushed} variant="saved" tripId="trip-1" baseRevisionId="revision-1" onApplied={() => undefined} />);

  assert.match(html, /今天稍微赶了一点/);
  assert.match(html, /帮我松一点/);
  assert.match(html, /aria-label="让第 1 天轻松一些"/);
});

test("saved route preview sends only a user goal to the server-authoritative repair endpoint", () => {
  const source = `${readFileSync(componentPath, "utf8")}\n${readFileSync(savedRoadbookPath, "utf8")}\n${readFileSync(repairPreviewPath, "utf8")}\n${readFileSync(repairModelPath, "utf8")}`;
  assert.match(source, /previewLocalRelaxDayRepair/);
  assert.match(source, /applyPersistedMutationProposal/);
  assert.match(source, /undoPersistedRevision/);
  assert.match(source, /X-Idempotency-Key/);
  assert.match(source, /路线刚刚发生了变化/);
  assert.match(source, /你的原路线仍然保持不变/);
  assert.match(source, /target_day: day, goal: "relax_day"/);
  assert.match(
    source,
    /repairFailureMessage\(response\.code, "preview"\),\s*reloadable: isStaleRouteMutation\(response\.code, response\.context\)/,
  );
  assert.match(
    source,
    /safeReplaceFailureMessage\(response\.code, "preview", response\.context\),\s*stopId: target\.stable_id \?\? undefined,\s*reloadable: isStaleRouteMutation\(response\.code, response\.context\)/,
  );
  assert.match(source, /应用这次调整/);
  assert.match(source, /保持原路线/);
  assert.match(source, /调整后的安排/);
  assert.match(source, /已锁定 · 已预留时间/);
  assert.match(source, /必去 · 你明确想去/);
  assert.doesNotMatch(source, /调整后的位置|LOCKED ·|MUST GO ·/);
  assert.match(source, /撤销刚才的调整/);
  assert.match(source, /重试撤销/);
  assert.match(source, /errorMessage/);
  assert.match(source, /proposal\.commands/);
  assert.match(source, /previewRequestIdRef/);
  assert.match(source, /requestId !== previewRequestIdRef\.current/);
  assert.match(source, /tabIndex=\{-1\}/);
  assert.match(source, /root\.focus\(\{ preventScroll: true \}\)/);
  assert.match(source, /window\.scrollTo\(\{ top, behavior \}\)/);
  assert.doesNotMatch(source, /rootRef\.current\?\.scrollIntoView/);
  assert.match(source, /autoFocus/);
  assert.match(source, /feedbackRef\.current\?\.focus/);
  assert.match(source, /repair\.status === "restored"\s*\?\s*<RepairFeedback autoFocus/);
  assert.match(source, /replace\.status === "restored"\s*\?\s*<RepairFeedback autoFocus/);
  assert.match(source, /repair\.status === "reloaded"\s*\?\s*<RepairFeedback autoFocus/);
  assert.match(source, /replace\.status === "reloaded"\s*\?\s*<RepairFeedback autoFocus/);
  assert.match(source, /eyebrow="ROUTE RESTORED"/);
  assert.match(source, /const repairInteractionActive =/);
  assert.match(source, /const replaceInteractionActive =/);
  assert.match(source, /if \(repairInteractionActive \|\| replaceInteractionActive\) return;/);
  assert.match(source, /target\.stable_id \|\| repairInteractionActive\) return;/);
  assert.doesNotMatch(source, /target\.stable_id \|\| repair\.status !== "idle"/);
  assert.match(source, /repairBlocked=\{replaceInteractionActive\}/);
  assert.match(source, /repairInteractionActive && \(replace\.status === "idle" \|\| replace\.status === "restored"\)/);
  assert.match(source, /replaceControlStatus: "available" \| "blocked"/);
  assert.match(source, /buildRoadbookRelaxAction/);
  assert.match(source, /blocked: "请先完成当前调整"/);
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

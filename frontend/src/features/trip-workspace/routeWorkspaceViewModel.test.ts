import assert from "node:assert/strict";
import test from "node:test";

import {
  getResultWorkspaceFixture,
  resultWorkspaceFixtures,
} from "../../components/trip/fixtures/resultWorkspaceFixtures.ts";
import {
  buildRouteWorkspaceContainerViewModel,
  buildRouteWorkspaceExecutionTrustViewModel,
  buildRouteWorkspaceSheetCopy,
  type RouteWorkspaceItinerary,
} from "./routeWorkspaceViewModel.ts";

test("builds stable shell and overview state for an executable fixture", () => {
  const fixture = getResultWorkspaceFixture("complete");
  const viewModel = buildRouteWorkspaceContainerViewModel({
    city: fixture.city,
    itinerary: adaptFixture(fixture),
    editing: false,
    activeSheet: null,
    autoFilledCount: 4,
    intentLine: "西湖文化线",
    executionLine: "路线骨架基本可执行",
    weakestDay: null,
  });

  assert.equal(viewModel.shell.statusLabel, "骨架可走");
  assert.equal(viewModel.shell.statusTone, "stable");
  assert.equal(viewModel.shell.subtitle, "先顺着路线看一遍。想改顺序、删点或继续补全时，再进入编辑。");
  assert.equal(viewModel.overview.completeness, 94);
  assert.equal(viewModel.overview.pendingTaskCount, 0);
  assert.equal(viewModel.overview.autoFilledCount, 4);
  assert.equal(viewModel.overview.intentLine, "西湖文化线");
  assert.equal(viewModel.executionTrust.status, "ready");
  assert.equal(viewModel.executionTrust.contextFacts[0]?.stateLabel, "已记录");
});

test("keeps route-risk fixtures in attention state without changing the itinerary contract", () => {
  const fixture = getResultWorkspaceFixture("route-risk");
  const viewModel = buildRouteWorkspaceContainerViewModel({
    city: fixture.city,
    itinerary: adaptFixture(fixture),
    editing: true,
    activeSheet: "completion",
    autoFilledCount: 4,
    intentLine: null,
    executionLine: null,
    weakestDay: { day: 3, reason: "离开前跨区移动偏长" },
  });

  assert.equal(viewModel.shell.statusLabel, "还有空缺");
  assert.equal(viewModel.shell.statusTone, "attention");
  assert.equal(viewModel.shell.subtitle, "拖动、锁定、删除或先放进待规划，完成后这版会成为当前计划。");
  assert.equal(viewModel.shell.sheetTitle, "补全这条路线");
  assert.equal(viewModel.overview.realismStatus, "needs_repair");
  assert.deepEqual(viewModel.overview.weakestDay, { day: 3, reason: "离开前跨区移动偏长" });
});

test("fixture workspace covers complete, sparse, route-risk, and missing-data cases", () => {
  assert.deepEqual(
    resultWorkspaceFixtures.map((fixture) => fixture.key),
    ["complete", "minor-gaps", "route-risk", "missing-data"],
  );

  const missingData = getResultWorkspaceFixture("missing-data");
  assert.equal(Object.keys(missingData.routePreviewMap).length, 0);
  assert.equal(missingData.poiDetailFixtures["良渚博物院"], undefined);
});

test("documents every workspace action sheet copy", () => {
  assert.deepEqual(buildRouteWorkspaceSheetCopy(null), {});
  assert.match(buildRouteWorkspaceSheetCopy("adjust").description ?? "", /一句话/);
  assert.match(buildRouteWorkspaceSheetCopy("share").title ?? "", /分享/);
  assert.match(buildRouteWorkspaceSheetCopy("more").description ?? "", /住宿/);
});

test("keeps missing, stale, conflicting, and heuristic execution facts distinct", () => {
  const trust = buildRouteWorkspaceExecutionTrustViewModel({
    status: "needs_attention",
    headline: "路线仍有待核实的执行事实。",
    blocking_reasons: [],
    warning_reasons: ["部分路线没有可验证的 provider 数据。"],
    facts: [
      {
        key: "route-data",
        category: "route",
        status: "missing",
        source_kind: "missing_data",
        verification_status: "unavailable",
        freshness_status: "unknown",
        label: "路线数据",
        detail: "两段路线只使用了本地估算。",
        count: 2,
      },
      {
        key: "place-data",
        category: "place",
        status: "stale",
        source_kind: "provider",
        verification_status: "provider_returned",
        freshness_status: "stale",
        label: "地点详情",
        detail: "地点信息需要刷新后再确认。",
        count: 1,
      },
      {
        key: "execution-conflict",
        category: "execution",
        status: "conflicting",
        source_kind: "deterministic",
        verification_status: "not_applicable",
        freshness_status: "not_applicable",
        label: "执行冲突",
        detail: "离开前的移动和时间边界冲突。",
        count: 1,
      },
      {
        key: "system-suggestions",
        category: "schedule",
        status: "heuristic",
        source_kind: "heuristic",
        verification_status: "not_applicable",
        freshness_status: "not_applicable",
        label: "系统补充",
        detail: "这些停留点是系统建议。",
        count: 3,
      },
    ],
  });

  assert.equal(trust.statusLabel, "需要处理");
  assert.equal(trust.blockingFacts[0]?.stateLabel, "存在冲突");
  assert.equal(trust.warningFacts[0]?.stateLabel, "信息缺失");
  assert.equal(trust.warningFacts[1]?.stateLabel, "已过期");
  assert.equal(trust.contextFacts[0]?.stateLabel, "系统判断");
  assert.match(trust.warningFacts[0]?.freshnessLabel ?? "", /未记录/);
  assert.match(trust.contextFacts[0]?.detail ?? "", /不等同于用户确认/);
});

type FixtureLike = ReturnType<typeof getResultWorkspaceFixture>;

function adaptFixture(fixture: FixtureLike): RouteWorkspaceItinerary {
  return {
    ...fixture.itinerary,
    trip_days: fixture.tripDays,
    planner_realism: fixture.plannerRealism,
    execution_trust: fixture.executionTrust,
    completion_intelligence: fixture.completion,
  };
}

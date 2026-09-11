import assert from "node:assert/strict";
import test from "node:test";

import {
  getResultWorkspaceFixture,
  resultWorkspaceFixtures,
} from "../../components/trip/fixtures/resultWorkspaceFixtures.ts";
import {
  buildRouteWorkspaceContainerViewModel,
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
  assert.deepEqual(viewModel.shell.completionAction, {
    headerLabel: "检查路线",
    label: "检查",
    hint: "路线",
  });
  assert.equal(viewModel.overview.completeness, 94);
  assert.equal(viewModel.overview.pendingTaskCount, 0);
  assert.equal(viewModel.overview.autoFilledCount, 4);
  assert.equal(viewModel.overview.intentLine, "西湖文化线");
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
  assert.deepEqual(viewModel.shell.completionAction, {
    headerLabel: "修复空缺",
    label: "补全",
    hint: "修空缺",
  });
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
  assert.deepEqual(buildRouteWorkspaceSheetCopy("completion", false), {
    title: "路线检查",
    description: "当前没有待补齐项目；可以按需查看路线依据和已保护边界。",
  });
});

type FixtureLike = ReturnType<typeof getResultWorkspaceFixture>;

function adaptFixture(fixture: FixtureLike): RouteWorkspaceItinerary {
  return {
    ...fixture.itinerary,
    trip_days: fixture.tripDays,
    planner_realism: fixture.plannerRealism,
    completion_intelligence: fixture.completion,
  };
}

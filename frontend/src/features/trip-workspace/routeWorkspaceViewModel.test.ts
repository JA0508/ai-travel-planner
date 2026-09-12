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

test("prioritizes route risks ahead of unrelated completion tasks", () => {
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

  assert.equal(viewModel.shell.statusLabel, "先看风险");
  assert.equal(viewModel.shell.statusTone, "attention");
  assert.equal(
    viewModel.shell.subtitle,
    "第 3 天：离开前移动偏长。良渚博物院到杭州东站的路线段较长，可能压缩离站缓冲。",
  );
  assert.deepEqual(viewModel.shell.completionAction, {
    headerLabel: "其他补全",
    label: "补全",
    hint: "其他项",
  });
  assert.equal(viewModel.shell.completionPriority, "secondary");
  assert.equal(viewModel.shell.showCompletionHeader, false);
  assert.deepEqual(viewModel.shell.primaryRouteFocus, {
    day: 3,
    label: "查看第 3 天风险",
  });
  assert.equal(viewModel.shell.sheetTitle, "补全其他信息");
  assert.equal(
    viewModel.shell.sheetDescription,
    "这些是路线风险之外的空缺；处理它们不会替代路线风险确认。",
  );
  assert.equal(viewModel.overview.realismStatus, "needs_repair");
  assert.deepEqual(viewModel.overview.weakestDay, { day: 3, reason: "离开前跨区移动偏长" });
});

test("does not promote completion when a route risk has no reliable target day", () => {
  const fixture = getResultWorkspaceFixture("route-risk");
  const itinerary = adaptFixture(fixture);
  const viewModel = buildRouteWorkspaceContainerViewModel({
    city: fixture.city,
    itinerary: {
      ...itinerary,
      planner_realism: {
        status: "needs_repair",
        headline: "路线需要复核",
        issues: [{
          severity: "high",
          title: "跨区移动偏长",
          detail: "有一段跨区移动需要复核。",
        }],
      },
    },
    editing: false,
    activeSheet: null,
    autoFilledCount: 4,
    intentLine: null,
    executionLine: null,
    weakestDay: null,
  });

  assert.equal(viewModel.shell.statusLabel, "先看风险");
  assert.equal(
    viewModel.shell.subtitle,
    "路线有待复核的风险；暂时无法定位到具体日期，先查看路线依据再决定是否调整。",
  );
  assert.equal(viewModel.shell.showCompletionHeader, false);
  assert.equal(viewModel.shell.primaryRouteFocus, undefined);
  assert.deepEqual(viewModel.shell.completionAction, {
    headerLabel: "其他补全",
    label: "补全",
    hint: "其他项",
  });
});

test("does not fabricate a focus day when structured risk detail is unavailable", () => {
  const fixture = getResultWorkspaceFixture("route-risk");
  const itinerary = adaptFixture(fixture);
  const viewModel = buildRouteWorkspaceContainerViewModel({
    city: fixture.city,
    itinerary: {
      ...itinerary,
      planner_realism: {
        status: "needs_repair",
        headline: "路线需要复核",
        issues: [],
      },
    },
    editing: false,
    activeSheet: null,
    autoFilledCount: 4,
    intentLine: null,
    executionLine: null,
    weakestDay: { day: 3, reason: "1 个路线风险还没收口，先修这里最能提升整趟体验。" },
  });

  assert.equal(
    viewModel.shell.subtitle,
    "路线有待复核的风险；暂时无法定位到具体日期，先查看路线依据再决定是否调整。",
  );
  assert.equal(viewModel.shell.primaryRouteFocus, undefined);
});

test("does not focus an invalid route-risk day", () => {
  const fixture = getResultWorkspaceFixture("route-risk");
  const itinerary = adaptFixture(fixture);
  const viewModel = buildRouteWorkspaceContainerViewModel({
    city: fixture.city,
    itinerary: {
      ...itinerary,
      planner_realism: {
        status: "needs_repair",
        headline: "路线需要复核",
        issues: [{
          day: 4,
          severity: "high",
          title: "跨区移动偏长",
          detail: "有一段跨区移动需要复核。",
        }],
      },
    },
    editing: false,
    activeSheet: null,
    autoFilledCount: 4,
    intentLine: null,
    executionLine: null,
    weakestDay: null,
  });

  assert.equal(viewModel.shell.primaryRouteFocus, undefined);
});

test("uses the day named by route-risk evidence instead of a completion-heavy fallback", () => {
  const fixture = getResultWorkspaceFixture("route-risk");
  const itinerary = adaptFixture(fixture);
  const viewModel = buildRouteWorkspaceContainerViewModel({
    city: fixture.city,
    itinerary: {
      ...itinerary,
      planner_realism: {
        status: "needs_repair",
        headline: "路线需要复核",
        issues: [{
          day: 2,
          severity: "high",
          title: "跨区移动偏长",
          detail: "下午安排跨区，可能压缩晚间缓冲。",
        }],
      },
    },
    editing: false,
    activeSheet: null,
    autoFilledCount: 4,
    intentLine: null,
    executionLine: null,
    weakestDay: { day: 1, reason: "3 个待补任务还没收口。" },
  });

  assert.equal(viewModel.shell.subtitle, "第 2 天：跨区移动偏长。下午安排跨区，可能压缩晚间缓冲。");
  assert.deepEqual(viewModel.shell.primaryRouteFocus, {
    day: 2,
    label: "查看第 2 天风险",
  });
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
  assert.deepEqual(buildRouteWorkspaceSheetCopy("completion", true, true), {
    title: "补全其他信息",
    description: "这些是路线风险之外的空缺；处理它们不会替代路线风险确认。",
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

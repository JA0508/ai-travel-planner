import assert from "node:assert/strict";
import test from "node:test";

import { buildRoadbookRelaxAction } from "./roadbookRepairAction";

test("labels an available relaxation control with its exact day", () => {
  assert.deepEqual(buildRoadbookRelaxAction({ day: 2, repairStatus: "idle", blocked: false }), {
    label: "帮我松一点",
    ariaLabel: "让第 2 天轻松一些",
    disabled: false,
    showArrow: true,
  });
});

test("names the actual repair state instead of an available action", () => {
  assert.deepEqual(buildRoadbookRelaxAction({ day: 2, repairStatus: "previewing", repairDay: 2, blocked: false }), {
    label: "正在评估调整…",
    ariaLabel: "正在评估第 2 天的放松调整",
    disabled: true,
    showArrow: false,
  });
  assert.deepEqual(buildRoadbookRelaxAction({ day: 1, repairStatus: "applying", repairDay: 2, blocked: false }), {
    label: "正在保存调整…",
    ariaLabel: "正在保存第 2 天的调整",
    disabled: true,
    showArrow: false,
  });
  assert.deepEqual(buildRoadbookRelaxAction({ day: 1, repairStatus: "undoing", repairDay: 2, blocked: false }), {
    label: "正在恢复路线…",
    ariaLabel: "正在恢复调整前的路线",
    disabled: true,
    showArrow: false,
  });
  assert.deepEqual(buildRoadbookRelaxAction({ day: 1, repairStatus: "review", repairDay: 2, blocked: false }), {
    label: "请先决定当前调整",
    ariaLabel: "请先决定第 2 天的调整，再开始新的调整",
    disabled: true,
    showArrow: false,
  });
});

test("explains that another adjustment must finish before a new one can start", () => {
  assert.deepEqual(buildRoadbookRelaxAction({ day: 3, repairStatus: "idle", blocked: true }), {
    label: "请先完成当前调整",
    ariaLabel: "请先完成当前调整，暂时不能调整第 3 天",
    disabled: true,
    showArrow: false,
  });
});

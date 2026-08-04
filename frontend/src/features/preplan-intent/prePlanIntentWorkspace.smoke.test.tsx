import assert from "node:assert/strict";
import test from "node:test";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { PrePlanIntentWorkspace } from "./PrePlanIntentWorkspace";

const componentPath = fileURLToPath(new URL("./PrePlanIntentWorkspace.tsx", import.meta.url));

test("pre-plan workspace starts with a plain-language confirmation surface", () => {
  const html = renderToStaticMarkup(
    <PrePlanIntentWorkspace
      tripId="trip_draft_1"
      directUserText="我想去西安玩三天，白天看历史景点，晚上吃东西。"
      onCancel={() => undefined}
      onApplied={() => undefined}
    />,
  );
  assert.match(html, /确认行程信息/);
  assert.match(html, /确认几个关键信息后，我们会为你生成第一版行程/);
  assert.match(html, /正在整理你的旅行需求/);
  assert.doesNotMatch(html, /Intent Contract/);
  assert.doesNotMatch(html, /field_path/);
  assert.doesNotMatch(html, /provenance graph/i);
});

test("pre-plan bootstrap restores an existing intent before compiling a new Draft revision", () => {
  const source = readFileSync(componentPath, "utf8");
  assert.match(source, /autoCompileTripRef/);
  assert.match(source, /compileInFlightRef/);
  assert.match(source, /void bootstrapIntent\(\)/);
  assert.match(source, /if \(result\.ok\) \{[\s\S]*hydrateLatestIntent\(result\.data\)/);
  assert.match(source, /if \(result\.code === "intent_edit_no_longer_applicable"\) \{[\s\S]*await compileIntent\(\)/);
  assert.match(source, /void compileIntent\(\)/);
  assert.doesNotMatch(source, /编译意图合同/);
  assert.doesNotMatch(source, /field\.field_path/);
  assert.doesNotMatch(source, /semantic_digest/);
  assert.doesNotMatch(source, /provenance_graph/);
  assert.match(source, /确认行程信息/);
  assert.match(source, /一定想去/);
  assert.match(source, /查看依据/);
  assert.match(source, /重新识别/);
});

test("pre-plan workspace connects critical edits and clarification answers to server state", () => {
  const source = readFileSync(componentPath, "utf8");
  assert.match(source, /update_destination/);
  assert.match(source, /update_date_policy/);
  assert.match(source, /update_trip_days/);
  assert.match(source, /update_pace/);
  assert.match(source, /resolvePrePlanIntentClarification/);
  assert.match(source, /base_draft_version/);
  assert.match(source, /X-Idempotency-Key/);
  assert.match(source, /网络连接失败，你的修改还在这里/);
  assert.match(source, /行程信息已经在其他页面更新/);
  assert.match(source, /重新应用我的修改/);
  assert.match(source, /restoreFocusAfterSuccess/);
  assert.match(source, /preplan-primary-action/);
  assert.match(source, /getLatestPrePlanIntent/);
  assert.doesNotMatch(source, /localStorage/);
});

test("pre-plan workspace keeps a stale frozen preview visible and requires replacement before apply", () => {
  const source = readFileSync(componentPath, "utf8");
  assert.match(source, /buildPrePlanHandoffStatus/);
  assert.match(source, /data-preplan-handoff-status="stale"/);
  assert.match(source, /路线预览已过期/);
  assert.match(source, /重新生成路线预览/);
  assert.match(source, /preview\.draft_intent_revision_id/);
  assert.match(source, /userFacingPrePlanHandoffError/);
});

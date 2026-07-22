import assert from "node:assert/strict";
import test from "node:test";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { PrePlanIntentWorkspace } from "./PrePlanIntentWorkspace";

test("pre-plan workspace exposes compile, frozen preview, and Revision 1 confirmation in order", () => {
  const html = renderToStaticMarkup(
    <PrePlanIntentWorkspace
      tripId="trip_draft_1"
      directUserText="我想去西安玩三天，白天看历史景点，晚上吃东西。"
      onCancel={() => undefined}
      onApplied={() => undefined}
    />,
  );
  assert.match(html, /DRAFT TRIP/);
  assert.match(html, /先确认意图与来源，再生成第一版路线/);
  assert.match(html, /编译意图合同/);
  assert.match(html, /生成路线预览/);
  assert.match(html, /确认并创建 Revision 1/);
  assert.doesNotMatch(html, /直接生成行程/);
});

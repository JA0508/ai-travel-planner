import assert from "node:assert/strict";
import test from "node:test";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { PrePlanIntentWorkspace } from "./PrePlanIntentWorkspace";

test("pre-plan workspace exposes source review, contract compilation, frozen preview, and Revision 1 confirmation", () => {
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
  assert.match(html, /来源输入/);
  assert.match(html, /意图合同/);
  assert.match(html, /冻结预览/);
  assert.match(html, /直接用户输入/);
  assert.match(html, /1\. 编译意图合同/);
  assert.match(html, /2\. 生成冻结预览/);
  assert.match(html, /确认并创建 Revision 1/);
  assert.doesNotMatch(html, /直接生成行程/);
});

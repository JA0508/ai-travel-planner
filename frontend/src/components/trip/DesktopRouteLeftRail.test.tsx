import assert from "node:assert/strict";
import test from "node:test";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";

import { DesktopRouteLeftRail } from "./DesktopRouteLeftRail";

test("describes completion tasks as secondary when a route risk needs attention first", () => {
  const html = renderToStaticMarkup(
    <DesktopRouteLeftRail
      completionPriority="secondary"
      completion={<div>补全内容</div>}
      brief={<div>旅行边界</div>}
    />,
  );

  assert.match(html, /路线之外还能补什么/);
  assert.match(html, /先处理上方路线风险/);
  assert.doesNotMatch(html, /优先修哪里/);
});

test("keeps completion tasks primary when no route risk is present", () => {
  const html = renderToStaticMarkup(
    <DesktopRouteLeftRail completion={<div>补全内容</div>} brief={<div>旅行边界</div>} />,
  );

  assert.match(html, /优先修哪里/);
});

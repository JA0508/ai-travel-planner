import assert from "node:assert/strict";
import test from "node:test";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";

import { RouteWorkspaceShell } from "./RouteWorkspaceShell";

function renderShell(showCompletionHeader = true) {
  return renderToStaticMarkup(
    <RouteWorkspaceShell
      city="重庆"
      tripDays={3}
      statusLabel="先看风险"
      subtitle="路线有待复核的风险。"
      completionAction={{ headerLabel: "其他补全", label: "补全", hint: "其他项" }}
      showCompletionHeader={showCompletionHeader}
      editing={false}
      onToggleEditing={() => undefined}
      activeSheet={null}
      onSheetChange={() => undefined}
    >
      <div>路线内容</div>
    </RouteWorkspaceShell>,
  );
}

test("names the evidence action explicitly when route attention suppresses completion", () => {
  const html = renderShell(false);

  assert.match(html, />风险依据</);
  assert.doesNotMatch(html, />依据</);
});

test("keeps the general evidence label when completion remains primary", () => {
  const html = renderShell();

  assert.match(html, />依据</);
  assert.doesNotMatch(html, />风险依据</);
});

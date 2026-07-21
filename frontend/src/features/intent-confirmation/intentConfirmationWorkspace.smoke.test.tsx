import assert from "node:assert/strict";
import test from "node:test";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { IntentConfirmationWorkspace } from "./IntentConfirmationWorkspace";

test("browser smoke renders intent confirmation workspace without planner controls", () => {
  const html = renderToStaticMarkup(
    <IntentConfirmationWorkspace
      tripPersistence={{ status: "saved", tripId: "trip_1", currentRevisionId: "rev_1", revisionNumber: 1 }}
      directUserText="城市：上海"
    />,
  );
  assert.match(html, /Intent Confirmation Workspace/);
  assert.match(html, /Source-linked confirmation/);
  assert.doesNotMatch(html, /Generate itinerary/);
});

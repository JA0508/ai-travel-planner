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

test("browser smoke keeps unsaved trips at the intent boundary", () => {
  const html = renderToStaticMarkup(
    <IntentConfirmationWorkspace
      tripPersistence={{ status: "dirty", tripId: "trip_1", currentRevisionId: "rev_1", revisionNumber: 1, reason: "local edits" }}
      directUserText="城市：上海"
    />,
  );
  assert.match(html, /Compile the saved trip inputs/);
  assert.doesNotMatch(html, /Run scheduler/);
  assert.doesNotMatch(html, /Create TripRevision/);
});

test("browser smoke does not expose direct candidate admission controls", () => {
  const html = renderToStaticMarkup(
    <IntentConfirmationWorkspace
      tripPersistence={{ status: "saved", tripId: "trip_1", currentRevisionId: "rev_1", revisionNumber: 1 }}
      directUserText="豫园和外滩都想去"
    />,
  );
  assert.match(html, /Intent contract/);
  assert.doesNotMatch(html, /Add to itinerary/);
  assert.doesNotMatch(html, /Auto admit/);
});

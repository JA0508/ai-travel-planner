import assert from "node:assert/strict";
import test from "node:test";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { IntentConfirmationWorkspace } from "./IntentConfirmationWorkspace";

const componentPath = fileURLToPath(new URL("./IntentConfirmationWorkspace.tsx", import.meta.url));

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

test("workspace preserves a stale edit for explicit latest-revision reapply", () => {
  const source = readFileSync(componentPath, "utf-8");
  assert.match(source, /stale_intent_revision/);
  assert.match(source, /Your draft is retained/);
  assert.match(source, /Reapply to latest/);
  assert.match(source, /trip-import-evidence-focus/);
  assert.match(source, /latestIntentRevision/);
  assert.match(source, /loadedIntentRevision/);
  assert.match(source, /editingBaseIntentRevision/);
  assert.equal(source.includes("history[0]"), false);
});

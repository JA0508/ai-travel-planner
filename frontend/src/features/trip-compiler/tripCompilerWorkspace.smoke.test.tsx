import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import { fileURLToPath } from "node:url";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";

import { TripCompilerWorkspace } from "./TripCompilerWorkspace";

const componentPath = fileURLToPath(new URL("./TripCompilerWorkspace.tsx", import.meta.url));

test("trip compiler starts with one clear text input and no technical fields", () => {
  const html = renderToStaticMarkup(<TripCompilerWorkspace />);
  assert.match(html, /把旅行想法，/);
  assert.match(html, /变成一份看得懂的路线。/);
  assert.match(html, /开始编排行程/);
  assert.match(html, /杭州两日轻松游/);
  assert.match(html, /shanghai-street-hero\.png/);
  assert.doesNotMatch(html, /revision_id/i);
  assert.doesNotMatch(html, /trace_id/i);
  assert.doesNotMatch(html, /schema version/i);
});

test("live compiler uses the immutable Draft Intent path before server candidate selection", () => {
  const source = readFileSync(componentPath, "utf8");
  assert.match(source, /createDraftTrip/);
  assert.match(source, /compilePrePlanIntent/);
  assert.match(source, /editPrePlanIntent/);
  assert.match(source, /createPrePlanIntentPlanningRun/);
  assert.match(source, /selectTripCompilerCandidate/);
  assert.match(source, /confirm_place_identity/);
  assert.match(source, /postTripJson/);
  assert.match(source, /getTripJson/);
  assert.match(source, /ExecutableRoutePreview/);
  assert.doesNotMatch(source, /fixtures\//);
  assert.doesNotMatch(source, /buildDayRelaxationPlan/);
  assert.doesNotMatch(source, /move_stop/);
  assert.doesNotMatch(source, /generateTripCompilerCandidates/);
  assert.doesNotMatch(source, /compileTripCompilerIntent/);
  assert.doesNotMatch(source, /planTripCompilerIntent/);
});

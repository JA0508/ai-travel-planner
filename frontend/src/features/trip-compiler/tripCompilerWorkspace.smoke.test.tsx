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
  assert.match(html, /把零散的旅行想法，变成一条能直接执行的路线。/);
  assert.match(html, /整理我的旅行想法/);
  assert.match(html, /杭州两日轻松游/);
  assert.doesNotMatch(html, /revision_id/i);
  assert.doesNotMatch(html, /trace_id/i);
  assert.doesNotMatch(html, /schema version/i);
});

test("live compiler never imports fixtures or creates a route before server candidate selection", () => {
  const source = readFileSync(componentPath, "utf8");
  assert.match(source, /compileTripCompilerIntent/);
  assert.match(source, /generateTripCompilerCandidates/);
  assert.match(source, /selectTripCompilerCandidate/);
  assert.match(source, /user_confirmation/);
  assert.match(source, /postTripJson/);
  assert.match(source, /getTripJson/);
  assert.match(source, /ExecutableRoutePreview/);
  assert.doesNotMatch(source, /fixtures\//);
  assert.doesNotMatch(source, /buildDayRelaxationPlan/);
  assert.doesNotMatch(source, /move_stop/);
  assert.doesNotMatch(source, /placementReason \?\?/);
  assert.doesNotMatch(source, /planTripCompilerIntent/);
});

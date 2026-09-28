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
  assert.match(html, /data-visual-shell="road-movie-v0"/);
  assert.match(html, /不用一次规划完/);
  assert.doesNotMatch(html, /revision_id/i);
  assert.doesNotMatch(html, /trace_id/i);
  assert.doesNotMatch(html, /schema version/i);
});

test("golden path keeps the confirmation surface in plain travel language", () => {
  const source = readFileSync(componentPath, "utf8");
  assert.match(source, /旅行简报/);
  assert.match(source, /已经留好的时间/);
  assert.match(source, /这些地方，想和你确认一下/);
  assert.match(source, /这段安排已固定，不会被随意改动/);
  assert.doesNotMatch(source, />Planning Run</);
  assert.doesNotMatch(source, />Revision</);
});

test("confirmation separates the traveler mention from provider candidates", () => {
  const source = readFileSync(componentPath, "utf8");

  assert.match(source, /你提到的地点/);
  assert.match(source, /尚未作为路线地点保存/);
  assert.match(source, /提供商候选（系统推荐）/);
  assert.match(source, /确认前不会加入路线/);
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
  assert.match(source, /onApplied=\{\(response\)/);
  assert.match(source, /saved: response/);
  assert.doesNotMatch(source, /fixtures\//);
  assert.doesNotMatch(source, /buildDayRelaxationPlan/);
  assert.doesNotMatch(source, /move_stop/);
  assert.doesNotMatch(source, /generateTripCompilerCandidates/);
  assert.doesNotMatch(source, /compileTripCompilerIntent/);
  assert.doesNotMatch(source, /planTripCompilerIntent/);
});

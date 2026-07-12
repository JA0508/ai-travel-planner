import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

import {
  getRouteWorkspaceRefreshPolicy,
  routeWorkspaceRefreshPolicies,
  type RouteWorkspaceMutationKind,
} from "./routeWorkspaceRefreshPolicy.ts";

test("documents refresh policy for every current route workspace mutation kind", () => {
  assert.deepEqual(
    Object.keys(routeWorkspaceRefreshPolicies).sort(),
    [
      "completion_task_apply",
      "completion_task_undo",
      "local_replan_mutation",
      "route_edit_commit",
    ],
  );
});

test("local replan mutation applies optimistically and then refreshes derived surfaces", () => {
  const policy = getRouteWorkspaceRefreshPolicy("local_replan_mutation");

  assert.equal(policy.itineraryUpdate, "local_patch");
  assert.equal(policy.refreshEndpoint, "refreshItinerarySurfaces");
  assert.equal(policy.refreshTiming, "after_local_patch");
  assert.equal(policy.failureBehavior, "preserve_local_itinerary");
  assert.ok(policy.refreshedSurfaces.includes("completion_intelligence"));
});

test("completion task apply remains backend-authoritative with idempotent execution", () => {
  const policy = getRouteWorkspaceRefreshPolicy("completion_task_apply");
  const pageSource = readFileSync(new URL("../../app/page.tsx", import.meta.url), "utf8");

  assert.equal(policy.itineraryUpdate, "backend_authoritative");
  assert.equal(policy.refreshEndpoint, "applyCompletionTask");
  assert.match(pageSource, /APPLY_COMPLETION_TASK_API_URL/);
  assert.match(pageSource, /X-Idempotency-Key/);
});

test("completion undo preserves local result if derived refresh fails", () => {
  const policy = getRouteWorkspaceRefreshPolicy("completion_task_undo");

  assert.equal(policy.itineraryUpdate, "local_patch");
  assert.equal(policy.refreshEndpoint, "refreshItinerarySurfaces");
  assert.equal(policy.failureBehavior, "preserve_local_itinerary");
});

test("route edit commit has no hidden backend refresh dependency", () => {
  const policy = getRouteWorkspaceRefreshPolicy("route_edit_commit");

  assert.equal(policy.itineraryUpdate, "local_patch");
  assert.equal(policy.refreshEndpoint, null);
  assert.deepEqual(policy.refreshedSurfaces, ["itinerary", "trip_intent"]);
});

test("all refresh policies use known mutation ids", () => {
  const mutationKinds: RouteWorkspaceMutationKind[] = [
    "route_edit_commit",
    "local_replan_mutation",
    "completion_task_apply",
    "completion_task_undo",
  ];

  for (const mutationKind of mutationKinds) {
    assert.equal(getRouteWorkspaceRefreshPolicy(mutationKind).mutationKind, mutationKind);
  }
});

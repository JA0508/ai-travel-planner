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
      "backend_replan_apply",
      "backend_replan_undo",
      "completion_task_apply",
      "completion_task_undo",
      "local_replan_mutation",
      "route_edit_commit",
      "swap_apply",
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

test("saved backend replan apply is server-authoritative and idempotent", () => {
  const policy = getRouteWorkspaceRefreshPolicy("backend_replan_apply");
  const pageSource = readFileSync(new URL("../../app/page.tsx", import.meta.url), "utf8");

  assert.equal(policy.itineraryUpdate, "backend_authoritative");
  assert.equal(policy.refreshEndpoint, "applyPersistedReplanProposal");
  assert.equal(policy.refreshTiming, "during_backend_mutation");
  assert.match(pageSource, /previewPersistedReplan/);
  assert.match(pageSource, /applyPersistedReplanProposal/);
  assert.match(pageSource, /buildReplanProposalIdempotencyKey/);
  assert.match(pageSource, /proposal_digest/);
  assert.doesNotMatch(pageSource, /expected_preview_digest/);
});

test("saved backend replan undo is a server-authoritative compensating revision", () => {
  const policy = getRouteWorkspaceRefreshPolicy("backend_replan_undo");
  const pageSource = readFileSync(new URL("../../app/page.tsx", import.meta.url), "utf8");

  assert.equal(policy.itineraryUpdate, "backend_authoritative");
  assert.equal(policy.refreshEndpoint, "undoPersistedRevision");
  assert.match(pageSource, /undoPersistedReplanRevision/);
  assert.match(pageSource, /undo-replan:/);
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

test("saved route edit commit is server-authoritative through typed mutation proposal", () => {
  const policy = getRouteWorkspaceRefreshPolicy("route_edit_commit");
  const pageSource = readFileSync(new URL("../../app/page.tsx", import.meta.url), "utf8");

  assert.equal(policy.itineraryUpdate, "backend_authoritative");
  assert.equal(policy.refreshEndpoint, "applyPersistedMutationProposal");
  assert.match(pageSource, /previewPersistedMutation/);
  assert.match(pageSource, /applyPersistedMutationProposal/);
  assert.match(pageSource, /buildRouteEditCommandEnvelope/);
});

test("saved swap apply is server-authoritative through typed replacement command", () => {
  const policy = getRouteWorkspaceRefreshPolicy("swap_apply");
  const pageSource = readFileSync(new URL("../../app/page.tsx", import.meta.url), "utf8");

  assert.equal(policy.itineraryUpdate, "backend_authoritative");
  assert.equal(policy.refreshEndpoint, "applyPersistedMutationProposal");
  assert.match(pageSource, /buildSwapReplaceCommandEnvelope/);
});

test("all refresh policies use known mutation ids", () => {
  const mutationKinds: RouteWorkspaceMutationKind[] = [
    "route_edit_commit",
    "local_replan_mutation",
    "backend_replan_apply",
    "backend_replan_undo",
    "completion_task_apply",
    "completion_task_undo",
    "swap_apply",
  ];

  for (const mutationKind of mutationKinds) {
    assert.equal(getRouteWorkspaceRefreshPolicy(mutationKind).mutationKind, mutationKind);
  }
});

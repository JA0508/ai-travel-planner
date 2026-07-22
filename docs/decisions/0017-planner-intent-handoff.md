# ADR 0017: Frozen Planner Intent Handoff

## Status

Accepted for F-004b draft delivery.

## Date

2026-07-22

## Context

F-004a produces an immutable, source-linked and planner-ready intent contract,
but it deliberately does not execute the planner or create a `TripRevision`.
Letting the browser reconstruct planner inputs, or re-running the planner at
confirmation time, would break preview/apply integrity and detach scheduled
items from the reviewed evidence that admitted them.

## Decision

- Build `PlannerHandoffInput` only from the latest verified formal contract.
  It contains policy versions, semantic and lineage digests, canonical candidate
  identity, coordinates, structured boundaries, windows, fixed events and
  source-link identifiers. It never contains raw prompt text or raw LLM output.
- Reject unresolved contracts, legacy/unverified candidates, multi-destination
  handoffs and fixed events without a verified canonical TripCandidate. The
  first F-004b slice supports one destination rather than silently collapsing a
  multi-city intent.
- Persist an append-only `planner_handoff_runs` record and its pending mutation
  proposal in one SQLite transaction. The run stores the frozen input, trace,
  result, validation report and their digests.
- Apply the exact proposal snapshot in one SQLite transaction. The transaction
  verifies the current TripRevision, latest IntentRevision, run/proposal
  linkage, digest integrity and idempotency before it appends one
  `planner_intent_handoff` TripRevision.
- Carry candidate ID and formal field/provenance links into scheduled items so
  an executable snapshot remains navigable back to the intent evidence graph.

## Consequences

- A preview is not a saved itinerary. Only explicit apply promotes its frozen
  snapshot to the durable trip lineage.
- A stale intent edit cannot be applied through an older preview. Concurrent
  applies converge on the same immutable revision rather than creating sibling
  revisions.
- The existing Intent Confirmation Workspace gains an execution handoff panel;
  it does not create a second chat entry point or a page-level planner
  controller.
- Full Planner Trace review, provider fact refresh, multi-city planning and
  richer evaluation corpus expansion remain F-020b/F-005 follow-up work.

## Verification

- Planner handoff API characterization tests, including a two-connection SQLite
  apply race, stale intent rejection, fixed-event/boundary mapping and
  unverified identity rejection.
- Full backend suite, planner/mutation/import/intent evaluation gates, frontend
  typecheck, workspace tests, browser smoke and production build.

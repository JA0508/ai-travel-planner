# ADR 0014: Semantic Intent Contract and Atomic Append

## Status

Accepted for F-004a.2 draft delivery.

## Date

2026-07-21

## Context

F-004a.1 introduced typed intent sections, but the canonical contract still
depended on a generic field list, string evidence references, string
assumptions, and service-layer stale checks. That was not strong enough for a
planner handoff because two clients could still race between the latest-intent
precheck and append, and downstream code could not compare equivalent semantic
intent content independently from revision IDs or timestamps.

The product boundary requires reviewed source facts, direct language, user
overrides, and untrusted LLM proposals to become a deterministic,
source-linked, planner-ready contract before any scheduler, provider lookup, or
TripRevision mutation is allowed.

## Decision

Extend `SourceLinkedTripIntentEnvelope` with:

- field-level `semantic_type` and normalized `semantic_value`;
- source `authority` so UI and tests can distinguish user-confirmed,
  reviewed-source, saved-state, deterministic-context, and untrusted LLM
  evidence;
- `parser_result` that records parser status and input digests without storing
  private raw text;
- typed assumptions with `has_assumed_value` and `blocks_planner_ready`;
- explicit `readiness_policy`;
- `provenance_graph` nodes and edges;
- `semantic_digest`, stable across revisions with equivalent semantic content.

Move intent edit append protection into repository transactions with
`expected_parent_intent_revision_id` and `require_latest_parent`. Idempotent
replays are still resolved before stale-parent rejection.

Add intent-revision restore as an append-only intent operation. Restoring an old
intent revision creates a new `IntentRevision`; it does not restore a
`TripRevision`, mutate an itinerary, call the planner, or call providers.

## Consequences

### Positive

- Every selected field can answer what it means, where it came from, which
  authority won, whether it is confirmed, and which revision owns it.
- Equivalent intent content has a stable semantic digest even when stored in
  different immutable revisions.
- Missing values without an assumed value cannot be marked planner-ready.
- Concurrent edits cannot create sibling intent revisions from the same parent.
- The frontend can inspect history, detail, edit, restore, readiness, parser,
  digest, and provenance evidence without implying planner execution.

### Negative / trade-offs

- The envelope JSON is larger because provenance graph nodes and typed
  assumptions are persisted with each intent revision.
- Missing `trip_days` is now a planner-blocking clarification rather than a
  non-blocking assumption, which tightens F-004a.1 behavior.
- The provenance graph is intentionally compact and field-level; it is not yet a
  full Planner Trace.

## Alternatives considered

- Keep provenance as summary rows only. Rejected because F-004b needs explicit
  evidence edges and authority semantics.
- Rely on service-layer stale prechecks. Rejected because they cannot prove
  transaction-level compare-and-append under concurrent writes.
- Reuse `TripRevision` restore semantics. Rejected because F-004a.2 must remain
  an intent-contract boundary and must not mutate itineraries.

## Related documents

- `docs/product/PRODUCT_DIRECTION.md`
- `docs/product/CODEX_AI_TRAVEL_PLANNER_PRODUCT_SPEC.md`
- `docs/decisions/0012-source-linked-intent-contract.md`
- `docs/decisions/0013-typed-intent-contract-hardening.md`

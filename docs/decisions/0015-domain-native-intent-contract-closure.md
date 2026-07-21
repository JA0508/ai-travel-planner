# ADR 0015: Domain-Native Intent Contract Closure

## Status

Accepted for F-004a.3 draft delivery.

## Date

2026-07-21

## Context

F-004a.2 established semantic fields, source authority, provenance summaries,
semantic digests, and transaction-level latest-intent checks. The remaining
contract risk was that core values were still represented as generic `Any` or
`dict[str, Any]`, provenance was still mostly string evidence references, parser
failure states were not explicit, and clients could compile or restore without a
clear base intent revision.

F-004b needs a planner handoff input that can be audited without trusting old LLM
explanations or implicit UI state. The intent boundary must remain independent
from planner execution, scheduler execution, provider lookups, TripRevision
creation, and itinerary mutation.

## Decision

Close F-004a with a domain-native `SourceLinkedTripIntentEnvelope` contract:

- destination, trip days, pace, transport preference, must candidate, fixed
  event, general preference, budget, and traveler need values are represented by
  explicit domain value models;
- selected fields and `typed_intent` carry the same domain value shape instead of
  raw primitives or untyped dictionaries;
- `parser_result.status` records `unavailable`, `timeout`, `invalid`, and
  `provider_error` in addition to normal parse states;
- provenance graph construction lifts existing evidence refs into structured
  candidate, artifact, mention, review decision, page, and bounding-box nodes
  where those references are present;
- compile and restore requests can carry `base_intent_revision_id` so stale
  clients cannot append against an unseen intent revision;
- intent append transactions verify both the current TripRevision and latest
  parent intent revision before insert, and reject revision-number mismatches;
- `semantic_digest` is separated from `lineage_digest` so equivalent intent
  content can be compared independently from revision ownership.

The existing flat `planner_ready_intent` preview remains for compatibility and
for safe UI display, but it is derived from the domain-native fields.

## Consequences

### Positive

- Each planner-relevant intent field has an explicit type, authority, source,
  confirmation state, conflict/readiness status, and revision lineage.
- Equivalent semantic content remains comparable even when stored in different
  immutable revisions.
- Stale compile, edit, clarification, and restore paths have explicit lineage
  protection before planner handoff.
- The Intent Confirmation Workspace can show semantic/lineage digests and
  navigate evidence nodes without implying that planning has executed.
- Intent compiler evaluation now gates a broader 15-fixture corpus.

### Negative / trade-offs

- Envelope JSON is larger because values and evidence nodes are structured.
- The provenance graph is still an intent evidence graph, not a full Planner
  Trace. It should not be treated as route or scheduler reasoning.
- Some source refs are still parsed from compact evidence strings when older
  import records do not expose richer foreign-key metadata directly.

## Explicit non-goals

- No planner execution.
- No scheduler execution.
- No provider or route lookup.
- No TripRevision creation.
- No itinerary mutation.
- No candidate auto-admission.
- No F-004b implementation.

## Related documents

- `docs/product/PRODUCT_DIRECTION.md`
- `docs/product/CODEX_AI_TRAVEL_PLANNER_PRODUCT_SPEC.md`
- `docs/decisions/0012-source-linked-intent-contract.md`
- `docs/decisions/0013-typed-intent-contract-hardening.md`
- `docs/decisions/0014-semantic-intent-contract-and-atomic-append.md`

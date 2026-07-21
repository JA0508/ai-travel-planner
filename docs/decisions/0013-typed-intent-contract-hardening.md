# ADR 0013: Typed Intent Contract Hardening

## Status

Accepted for F-004a.1 draft delivery.

## Context

F-004a established immutable source-linked intent revisions, but the envelope was
still mainly a generic field list. F-004b planner handoff needs a typed contract
that can answer which sources support each destination, date policy, fixed event,
POI preference, pace, and transport preference before any itinerary execution.

Intent revisions also need edit concurrency protection. Without a stale-intent
guard, two clients can edit an older intent revision and create ambiguous lineage
before planner handoff.

## Decision

Extend `SourceLinkedTripIntentEnvelope` with:

- `typed_intent`, a typed read model grouped into destinations, date policy,
  fixed events, POI preferences, pace, transport preferences, assumptions, and
  unresolved questions.
- `provenance_summary`, a deterministic per-field source and evidence summary.
- generic clarification metadata that names the target field and answer type.
- stale intent revision protection for edit and clarification writes, while
  preserving idempotent retry replay.

The legacy `fields`, `conflicts`, `assumptions`, `clarification_queue`, and
`planner_ready_intent` surfaces remain for backward compatibility and tests.

## Consequences

- F-004b can consume a typed preview instead of reparsing loose fields.
- The UI can show source evidence without implying planner execution.
- Non-blocking missing information can remain visible as assumptions instead of
  blocking a planner-ready preview.
- Concurrent edits to old intent revisions fail explicitly instead of silently
  forking the contract.

## Non-Goals

- No planner execution.
- No scheduler changes.
- No TripRevision creation.
- No itinerary mutation.
- No provider lookup or automatic TripCandidate admission.

# ADR 0016: Intent Contract Integrity Repair

## Status

Proposed for F-004a completion review.

## Date

2026-07-21

## Context

The F-004a.3 foundation exposed three integrity gaps: `TripCandidate` evidence
could be reconstructed from strings rather than verified import records, the
evaluation corpus labeled ordinary compile calls as revision/concurrency cases,
and evidence nodes did not navigate to the existing private review surface.
Those gaps made the contract look more complete than its executable proof.

## Decision

- Persist an append-only `trip_candidate_evidence_links` record when a reviewed
  import commits a candidate. It carries artifact, import job, mention, review
  decision, resolution, document generation/page/span/bounding-box identity and
  a source digest.
- Rehydrate those records during intent compilation. A candidate without
  verifiable structured lineage remains `legacy_unverified` and creates a
  planner-blocking clarification rather than inheriting review authority.
- Keep semantic identity independent of provenance/authority/revision metadata;
  record all of that material in the separate lineage digest.
- Evaluate real compile/edit/restore/idempotent/stale and two-writer SQLite
  operations, with named invariants and deterministic reruns.
- Reuse the private Import Review workspace for source evidence navigation; no
  raw artifact text is copied into local storage or a second document viewer.

## Consequences

- F-004a has a verifiable candidate-to-reviewed-source chain and fails closed
  for historical records that lack one.
- A restored semantic contract can retain its semantic digest while receiving a
  distinct lineage digest and immutable revision number.
- Browser state distinguishes a stale draft from an applied edit and requires an
  explicit reapply against the latest revision.
- This ADR does not authorize planner execution, provider calls, TripRevision
  creation, itinerary mutation, candidate auto-admission, F-004b, or F-020b.

## Verification

- Backend contract and full-suite tests.
- `python -m tools.run_intent_compiler_evaluation --ci`.
- Frontend typecheck, workspace tests, and intent browser smoke.

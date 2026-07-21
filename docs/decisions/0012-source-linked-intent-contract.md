# ADR 0012: Source-Linked Intent Contract Foundation

## Status

Accepted for F-004a draft delivery.

## Context

The import pipeline can now produce reviewed mentions and TripCandidates, but those
facts must not flow directly into itinerary mutation or planner execution. F-004a
needs a contract that can explain where each intent field came from, whether it is
hard, soft, or an assumption, whether it was confirmed, and why conflicts or
clarifications exist.

## Decision

Introduce an immutable `SourceLinkedTripIntentEnvelope` revision stream under the
existing Trip boundary.

The compiler accepts reviewed TripCandidates, direct user language, structured user
overrides, existing Trip state, and optional untrusted LLM proposals. It then
deterministically produces selected fields, shadowed fields, conflicts,
assumptions, a clarification queue, and a planner-ready preview.

LLM proposal generation is isolated behind an adapter. The adapter can produce an
untrusted proposal, but deterministic compilation owns priority, validation, and
planner-readiness decisions.

Intent revisions are append-only and idempotent. Editing or answering a
clarification creates a new intent revision; it does not create a TripRevision,
change the itinerary, or call the scheduler.

## Consequences

- Intent confirmation can be reviewed before planner handoff.
- Manual structured overrides have higher authority than older LLM explanations.
- Fixed-event and hard-field conflicts can block planner readiness without
  mutating the saved trip.
- F-004b or later planner integration can consume the envelope as an admission
  contract instead of re-parsing free text.

## Non-Goals

- No planner execution.
- No TripRevision mutation.
- No scheduler changes.
- No direct document-to-itinerary mutation.

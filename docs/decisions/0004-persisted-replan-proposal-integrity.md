# ADR-0004: Persist Replan Proposals Before Applying Trip Mutations

## Status

In review

## Date

2026-07-15

## Context

F-001a made initial planning, completion apply, and restore durable through
`TripRevision`. Conversational replan apply still depended on recomputing the
planner at confirmation time from raw follow-up text.

That left the preview/apply boundary weaker than the Source-to-Executable
contract requires:

- preview and apply could run different planner executions
- apply still received raw user instruction text
- duplicate apply with a different idempotency key was not independently tied to
  the previewed proposal
- stale or expired preview state had no durable lifecycle
- undo could target older revisions if the caller supplied an old base

## Decision

Persist a `TripMutationProposal` during replan preview. The proposal stores the
canonical preview snapshot, content digest, proposal digest, planner lineage,
validation report, lifecycle status, expiry, and eventual applied revision ID.

Apply now receives only:

- proposal ID in the path
- base revision ID
- proposal digest
- idempotency key

Apply does not receive follow-up text and does not run the planner. It validates
the proposal digest, lifecycle, expiry, base revision, stored snapshot digest,
and current trip revision inside the repository transaction before creating the
immutable `TripRevision`.

Duplicate apply of an already-applied proposal returns the original applied
revision, even with a different idempotency key.

Undo for replan patches is limited to the current revision and creates a
compensating `replan_undo` revision that restores the parent snapshot. The same
idempotency key can be retried, but a second undo attempt with a new key fails
because the target is no longer current.

## Consequences

Positive:

- preview/apply integrity no longer depends on planner determinism at apply time
- raw follow-up text stays out of the apply request and stored proposal snapshot
- expired, stale, tampered, cancelled, invalidated, and already-applied proposals
  have explicit server behavior
- mutation replay evaluation can test proposal apply and undo as durable
  contracts

Trade-offs:

- proposal rows add a second append-mostly persistence concept beside revisions
- proposal expiry requires clients to regenerate preview after timeout
- only replan proposals are covered in this decision; typed route edit and swap
  mutations remain future F-001b work

## Non-goals

This ADR does not implement TripRevision for route edit, swap, manual reorder,
Universal Import, Planner Trace UI, collaboration, or booking workflows.

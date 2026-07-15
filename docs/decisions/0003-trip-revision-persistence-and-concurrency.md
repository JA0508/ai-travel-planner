# ADR-0003: Add TripRevision Persistence and Concurrency Foundation

## Status

In review

## Date

2026-07-15

## Context

The planner workspace could produce explainable itineraries, but the executable
trip state still lived mostly in request responses and frontend session state.
That made reload, backend restart, stale writes, lost responses, and history
restore ambiguous.

The Source-to-Executable direction requires a durable unit of change that can
answer which trip is current, which revision produced the visible itinerary, and
which planner lineage and operation created it.

## Decision

Add a Trip aggregate with an immutable `TripRevision` history. The current trip
state is resolved through `Trip.current_revision_id`, not by updating itinerary
JSON in place.

Each revision stores:

- a full canonical itinerary snapshot
- content digest
- parent lineage digest and lineage digest
- parent/base revision references
- source type and operation metadata
- optional planner trace linkage from F-020a

Each write also creates a `RevisionOperation` explaining why the revision exists.

Restore creates a new revision whose snapshot matches the target revision. It
does not roll back the current pointer to an old row or delete later history.

## Concurrency and Idempotency

Later writes require a base revision and `X-Idempotency-Key`.

The transaction checks idempotency before stale-base validation:

```text
same key + same request → return original revision
same key + different request → idempotency_conflict
different key + stale base → stale_base_revision
```

SQLite writes use explicit `BEGIN IMMEDIATE` transactions, foreign keys, unique
revision numbers, and append-only triggers for revisions and operations.

## Access Boundary

This foundation uses anonymous capability access:

- raw capability is generated server-side
- DB stores only a capability hash
- browser receives the capability only through an HttpOnly, SameSite=Strict cookie
- localStorage stores only trip ID and current revision ID

This is private-by-capability access, not formal user authentication. It is a
bridge to future account and collaboration models, not a replacement for them.

## Storage

SQLite is the current runtime adapter because the branch needs a local,
CI-repeatable persistence layer without adding external infrastructure. The
repository boundary keeps the future PostgreSQL migration path explicit.

## Consequences

Positive:

- reload and backend restart recover the same saved revision
- writes can reject stale bases without last-write-wins
- lost responses can be retried safely
- restore preserves complete history
- planner lineage can be linked without exposing a trace API

Trade-offs:

- SQLite is single-writer and local by default
- anonymous capability access is not account auth
- only selected mutation paths are persisted in this foundation
- remaining local edits must be clearly marked Dirty

## Non-goals

This ADR does not add accounts, Trip Library, collaboration, Universal Import,
Planner Trace UI, public sharing, arbitrary client snapshot overwrite, or cloud
synchronization.

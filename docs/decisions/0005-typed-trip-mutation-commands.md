# ADR-0005: Use Typed Trip Mutation Commands for Route Edits and Swaps

## Status

In review

## Date

2026-07-15

## Context

F-001a and F-001b made planning, completion apply, restore, and conversational
replan durable through `TripRevision` and persisted `TripMutationProposal`.
Route edit and swap still depended on frontend-owned itinerary snapshot
mutation. That made saved state ambiguous: the browser could project a route
change locally, but the server could not prove which stable stop was changed,
which invariant protected the mutation, or which derived route/readiness data
became stale.

The Source-to-Executable workspace requires executable trip changes to be
auditable, retryable, versioned, and protected from stale state. Arbitrary client
itinerary uploads would weaken that boundary because they mix user intent,
server-owned metadata, derived route fields, and revision provenance in one
opaque payload.

## Decision

Route edit and swap now use versioned typed mutation commands. The command
schema starts at `1.0`, and the mutation engine version starts at
`current-baseline`.

Supported commands are intentionally limited to current product behavior:

- `move_stop`
- `reorder_day`
- `remove_stop`
- `swap_stops`
- `replace_stop`

Commands target stable scheduled-item IDs, not DOM IDs, display names, or array
indexes. Existing snapshots without IDs remain readable; new persisted snapshots
are normalized with deterministic stable IDs. Move, reorder, swap, and replace
preserve the stable slot identity; remove deletes only the targeted ID.

A pure backend `TripMutationEngine` executes command batches in memory, validates
fixed-event protection and itinerary invariants, computes impact, invalidates
derived route/readiness/completion surfaces, and returns a canonical preview
snapshot. HTTP, cookies, database transactions, idempotency, and revision
creation stay outside the engine.

Preview uses:

```text
POST /trips/{trip_id}/mutations/preview
```

Apply uses:

```text
POST /trips/{trip_id}/mutation-proposals/{proposal_id}/apply
```

The preview endpoint persists the resulting snapshot in the existing
`TripMutationProposal` table with typed command metadata, command digest, impact
summary, and invalidated surfaces. Apply receives only base revision ID,
proposal digest, and an idempotency key. It does not rerun the mutation engine,
planner, geocoder, or route provider; it validates the persisted proposal and
creates an immutable `TripRevision`.

Undo for route edit and swap creates a current-only compensating
`mutation_undo` revision from the parent snapshot. It does not execute inverse
commands or move the current pointer backward.

## Consequences

Positive:

- route edits and swaps are server-authoritative saved mutations
- preview/apply parity is tied to persisted content and command digests
- lost responses can be retried without duplicate revisions
- stale proposals fail instead of overwriting newer revisions
- fixed events and schedule invariants are enforced by backend validation
- invalid route/readiness/completion surfaces are explicitly marked stale

Trade-offs:

- frontend projection remains useful for editing UX but is not canonical
- command coverage is finite and must be extended deliberately
- cross-block/day edits that imply time rescheduling still need explicit repair
  semantics rather than hidden planner reruns
- SQLite remains a local single-writer persistence adapter

## Non-goals

This ADR does not implement Completion Undo, Universal Import, Import Review
Inbox, collaboration, accounts, CRDT merge, arbitrary JSON Patch, route provider
redesign, or a generic itinerary snapshot overwrite API.

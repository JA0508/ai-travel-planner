# ADR-0006: Persist Trip Candidates and Admit Them Through Typed Mutations

## Status

Accepted

## Date

2026-07-15

## Context

After F-001a, F-001b.1, and F-001b.2, planning, completion apply, restore,
conversational replan, route edits, and swaps all had server-authoritative
`TripRevision` paths. The remaining high-risk gap was candidate handling:
manual pending stops, completion candidates, unplanned stops, candidate reject,
and completion undo still had browser-owned dirty behavior.

Those paths are not all the same kind of change. A candidate can be a place the
user might want, a completion suggestion, or a place-intelligence lead. It does
not become executable itinerary state until the user explicitly admits it into a
day and block and the backend can validate required execution facts.

Treating all candidate actions as itinerary mutations would create noisy
revisions and blur the distinction between source review and executable trip
changes. Treating candidate admission as a frontend snapshot overwrite would
break the Source-to-Executable boundary.

## Decision

The system now has a persisted `TripCandidate` domain for pending places and
workflow decisions.

Candidate intake and workflow decisions are durable but do not create
`TripRevision` records:

- register candidate
- deduplicate by content digest
- reject candidate
- defer candidate
- restore candidate to pending

Candidate admission is the boundary where a candidate becomes executable trip
state. Admission uses the same persisted proposal/apply infrastructure as route
edit and swap, but with a typed `candidate_admission` command:

```text
add_candidate_stop(candidate_id, target_day, target_block, placement)
```

The command references a server-owned candidate ID. It does not upload a local
itinerary snapshot or arbitrary place payload. The backend loads the candidate,
checks workflow state, verifies required execution facts, applies deterministic
invariants, persists a preview proposal, and then creates an immutable
`TripRevision` when the user confirms.

If the candidate lacks facts needed for execution, admission returns
`repair_required` instead of inventing coordinates, using zero travel time, or
silently scheduling a weak item.

Completion undo is closed as a current-only compensating revision for saved
completion patches. It does not locally delete a stop from the browser as the
canonical saved state.

## Consequences

### Positive

- pending candidates survive reload without becoming itinerary revisions
- reject/defer/restore decisions are auditable workflow state
- candidate admission is retry-safe, stale-state protected, and replayable
- admission records provenance from candidate source into the scheduled item
- missing location or duration facts create explicit repair state
- completion undo now preserves revision lineage

### Negative / trade-offs

- candidate intake requires additional persistence tables
- the frontend must refresh both itinerary and candidate workspace after
  admission
- admission is intentionally stricter than local drag/drop drafts and may reject
  candidates that need fact repair
- broader import review, OCR, PDF ingestion, and source extraction remain
  separate work

## Alternatives considered

- **Arbitrary itinerary snapshot apply:** rejected because it would let the
  browser overwrite server-owned trip state.
- **Candidate decisions as revisions:** rejected because reject/defer/restore do
  not change executable itinerary state.
- **Auto-repair missing facts during admission:** deferred because hidden
  geocoding or duration assumptions would weaken preview/apply integrity.

## Related documents

- ADR-0003: TripRevision Persistence and Concurrency
- ADR-0004: Persisted Replan Proposal Integrity
- ADR-0005: Typed Trip Mutation Commands

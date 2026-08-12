# Planning Run Ledger

A Planning Run is the durable record created after a confirmed `TravelIntent` is
compiled into comparable route candidates and before a Trip exists.

## Immutable snapshot

The run stores the canonical intent, constraint graph, policy and snapshot
contract versions, candidate snapshots, their hashes, and the candidate-set
hash. These values never change after creation. A run has one of `generated`,
`selecting`, `selected`, `expired`, or `invalidated` status.

`planning_run_events` is append-only. It records creation, generation,
selection attempts, rejection, selection, revision creation, expiry, and replay
verification without storing capabilities or raw source text.

## Access and lifecycle

The browser receives a HttpOnly `planning_run_capability` cookie when a run is
created. Reading, selecting, and reading the plain-language record all require
that capability. Runs remain readable after expiry, but are no longer
selectable. A selected run links exactly one Trip and Revision 1.

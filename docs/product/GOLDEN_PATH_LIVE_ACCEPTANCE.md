# Golden Path Live Acceptance

## URL boundary

- `/product-reset-preview`: fixture-only prototype, no backend calls.
- `/product-reset-live`: real Draft Trip, Intent Compiler, frozen planner
  handoff, SQLite-backed `TripRevision`, and server-authored repair.

## Acceptance scenarios

1. Hangzhou: natural language compiles to a two-day preview and, after explicit
   confirmation, creates revision 1 with returned route activity and movement
   metadata.
2. Shanghai: an appointment is executable only when it has a verified canonical
   candidate. It is rendered as `user_fixed` and cannot be selected by repair.
3. Xi'an: a rushed day can move exactly one automatic suggestion to an adjacent
   day; user-required and fixed activities remain unchanged; apply creates
   revision 2 and retries are idempotent.
4. A true hard conflict remains an error/blocked state and must not create
   revision 1.

## Required automated evidence

- API tests assert server-authored repair scope, protected-item preservation,
  atomic revision 2 creation, stale rejection, idempotent retry and zero
  parser/LLM/full-planner/provider calls.
- Production-build browser tests exercise the live URL at desktop and mobile,
  inspect console/page/network errors, and use a temporary SQLite database.

## Current contract limitation

An arbitrary fixed event without a verified `TripCandidate` remains blocked by
design. The live route must show that conflict rather than fabricate a place
identity from free text. A verified candidate is therefore a prerequisite for
the positive Shanghai appointment scenario.

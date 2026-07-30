# Golden Path Repair Policy

The golden-path repair is a bounded operation for `goal=relax_day`:

```text
saved revision + rushed target day
→ server selects one eligible system-suggested activity
→ adjacent day with relaxed/balanced capacity
→ typed move command and immutable proposal
→ explicit user apply
→ TripRevision N + 1
```

## Selection policy

1. The requested source day must be server-classified `rushed`.
2. The movable set is only `auto_seeded_poi`, `auto_seeded_meal`, and
   `auto_filled`, never an item marked fixed.
3. The receiving day must be adjacent and classified `relaxed` or `balanced`.
4. The next day wins over the previous day; remaining ties are stable by load
   and scheduled-item identity.
5. The existing mutation engine validates identity, overlap, availability,
   boundaries, duplicate places and unknown-route semantics before persistence.

The operation rejects an absent source day, a non-rushed day, no protected-safe
candidate, no safe adjacent capacity, stale base revision, expired proposal,
digest mismatch and idempotency-key reuse with a different request.

## What it does not do

It does not invoke the text parser, LLM proposal adapter, full planner,
scheduler, provider route API, candidate admission, or a whole-trip
regeneration. The affected legs are recomputed as explicitly labelled local
deterministic estimates; unavailable anchor coordinates remain unavailable.

The before/after snapshot, mutation command digest, validation report and
operation metadata are persisted through the normal proposal and revision
machinery. Apply never recomputes the proposal.

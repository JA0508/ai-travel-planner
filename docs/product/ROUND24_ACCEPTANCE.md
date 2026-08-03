# Round 24 Acceptance

Round 24 is complete only when all of the following are true:

1. A confirmed intent produces a provenance-linked `ConstraintGraph` and typed
   conflict cores before scheduling.
2. Hard conflicts return structured `422` responses and create neither Trip nor
   Revision.
3. Candidate generation is deterministic, parser-free, LLM-free, and leaves the
   trip table unchanged.
4. Returned candidates are stable, bounded to one through three, carry stable
   hashes and explainable Pareto/comparison metadata, and contain no dominated
   duplicate.
5. Selection verifies candidate id, hash, intent digest, and idempotency key;
   only the first valid selection creates Revision 1.
6. The route-first comparison UI supports source disclosure, mobile layout, and
   recoverable stale/expired errors without technical ids in default content.
7. API, unit, integration, workspace, build, and isolated browser tests cover
   normal planning, hard conflicts, determinism, Pareto filtering, selection
   idempotency, and source-preserving user confirmation edits.

Known V1 boundary: candidate proposals are short-lived server memory. Persisted
candidate comparison history is intentionally deferred, not silently implied.

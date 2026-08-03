# Plan Candidate Policy

## Candidate generation

`POST /trip-compiler/plan-candidates` accepts a typed confirmed intent. It does
not call an LLM or parser, and it does not create a Trip or TripRevision. The
server builds a `ConstraintGraph`, rejects hard conflict cores, and invokes the
existing deterministic itinerary builder with strategy-owned input variants:

- `relaxed`: preserve hard requirements and leave optional places uncommitted.
- `balanced`: preserve hard requirements and include eligible optional places.
- `low_travel`: preserve hard requirements and prefer the smallest optional set.

The candidate representation includes its immutable itinerary skeleton,
constraint graph, applied/relaxed/unsatisfied constraint ids, and measurable
metrics: fixed and must coverage, optional coverage, total travel minutes,
activity minutes, daily load, free buffer, and heuristic labels. It never has a
single opaque “best score”.

## Pareto policy

Candidate A dominates B only when A is no worse on all comparable dimensions and
strictly better on at least one. Coverage is maximized; travel, activity load,
and overload are minimized; free buffer is maximized. Equal skeletons collapse
to the canonical strategy order. The returned list is a stable Pareto frontier,
with at least one candidate and at most three.

The API returns comparison metadata explaining each visible trade-off. Missing
route information is reported as missing, never converted to zero.

## Selection policy

The server retains a short-lived, immutable candidate proposal after generation.
`POST /trip-compiler/plan-candidates/{candidate_id}/select` accepts only:

- `candidate_id`
- `candidate_hash`
- `intent_digest`
- `X-Idempotency-Key`

The server verifies the proposal has not expired, the hash and intent digest
match, and the idempotency key is not being reused for a different candidate.
Only then does it pass the server-held structured itinerary request into the
existing Trip persistence service, creating Revision 1. The browser never sends
a skeleton, schedule, or revision payload. Replaying the same key returns the
same persisted result; stale/expired candidates return a recoverable conflict.

The in-memory proposal store is deliberately bounded and is suitable for this
pre-plan V1 slice. A server restart invalidates unselected proposals and asks the
user to regenerate candidates; it does not create a partial trip.

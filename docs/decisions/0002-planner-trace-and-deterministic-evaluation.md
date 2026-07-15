# ADR-0002: Add Planner Trace and Deterministic Evaluation Baseline

## Status

Accepted

## Date

2026-07-13

## Context

The planner already produces explainable itinerary surfaces, but many of those
explanations are result-derived and user-facing. They are useful for the product
interface, but they are not enough to answer engineering questions such as:

- which candidates were seen before scheduling?
- which branch rejected a candidate?
- whether route data was known, missing, or locally estimated?
- whether a planner change preserved fixed constraints?
- whether a fixture can be replayed without live providers or an LLM?

The Source-to-Executable product direction requires planner behavior to be
explainable, reproducible, and regression-testable without turning traces into a
second execution authority.

## Decision

Add a versioned planner trace and deterministic evaluation baseline.

The trace is observational:

- it records decisions that the existing planner already makes
- it is append-only during a run
- it uses stable reason codes instead of free-text log parsing
- it separates deterministic payload from volatile metadata
- it produces a canonical digest for replay comparison
- it excludes raw prompts, secrets, booking codes, emails, phone numbers, and
  other private content

The evaluation runner uses fixture provider snapshots and invokes the production
planning path with provider calls patched to deterministic fixture providers. It
does not call Amap, OpenAI, or any live network service.

CI runs the deterministic evaluation command as part of the backend job.

## Consequences

### Positive

- Planner regressions can be caught with critical invariants, not only snapshots.
- Route/provider missing data remains distinguishable from zero-duration travel.
- Fixed event preservation, schedule overlap, duplicate scheduling, traceability,
  and privacy checks become repeatable.
- Future planner versions can compare trace digests and structured reason codes.
- The foundation supports later TripRevision and PlannerRun persistence.

### Negative / trade-offs

- Trace coverage is intentionally partial at first; not every helper emits events.
- The evaluation corpus is fixture-sized, not a complete production benchmark.
- Provider snapshots store replay facts, not raw third-party responses.
- Trace is not yet persisted or exposed through a user-facing UI.
- Some current planner branches still surface through result summaries rather than
  dedicated trace events.

## Alternatives considered

### Parse logs

Rejected because free-text logs are unstable, privacy-sensitive, and hard to use
as CI regression gates.

### Full itinerary golden snapshots

Rejected as the primary strategy because entire itinerary snapshots are brittle.
The baseline uses critical invariants, semantic expectations, and digest
comparison instead.

### LLM-as-judge planner scoring

Rejected for this baseline because subjective model scoring is not deterministic.
LLM evaluation may be added later only as an auxiliary, versioned signal.

### Public trace API

Rejected for this stage. Trace export remains backend/test/dev infrastructure and
does not create a public unauthenticated trace endpoint.

## Related documents

- `docs/product/PRODUCT_DIRECTION.md`
- `docs/product/CODEX_AI_TRAVEL_PLANNER_PRODUCT_SPEC.md`
- `docs/decisions/0001-source-to-executable-trip-workspace.md`

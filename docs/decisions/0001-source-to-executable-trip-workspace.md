# ADR-0001: Adopt Source-to-Executable Trip Workspace as the product architecture

## Status

Accepted

## Date

2026-07-12

## Context

Generic AI itinerary generation has become highly commoditized. A model connected
to a map API can produce a visually plausible multi-day route, but this does not
reliably solve the harder travel-planning problems:

- users begin with fragmented guides, screenshots, notes, and reservations
- place identity can be ambiguous
- hard and soft constraints must be distinguished
- route and operational facts can be incomplete or stale
- changes should not silently break fixed events
- collaborators need a shared decision history
- planning quality should be reproducible and testable

The repository already contains a valuable foundation in deterministic scheduling,
Trip Readiness, Completion Intelligence, Planner Realism, route workspace design,
and Place Intelligence.

A stronger product identity is needed to keep future development aligned.

## Decision

The product will be developed as a:

> **Source-to-Executable Trip Workspace**

The system will compile fragmented travel sources and user intent into an itinerary
that is explainable, constraint-safe, source-traceable, reviewable, versioned, and
repairable.

The canonical flow is:

```text
SourceArtifact
→ ExtractedMention
→ CanonicalPlace / PlaceFact
→ TripIntentEnvelope
→ PlannerRun / DecisionTrace
→ TripRevision
→ PatchLog
→ ReadinessSnapshot
→ Executable Trip
```

The durable unit of change is a `TripRevision`, produced by applying a validated
patch to a base revision.

LLMs may interpret, classify, propose, summarize, and explain.

Deterministic systems must own identity resolution, date/time calculation, route
facts, hard constraints, validation, patch application, revision control,
permissions, idempotency, and stale-state protection.

## Consequences

### Positive

- Differentiates the project from generic AI itinerary generators.
- Creates a coherent path from content import to real execution.
- Makes provenance, uncertainty, and safety visible.
- Supports impact previews, undo, replay, and collaboration.
- Preserves the existing deterministic scheduler as a core advantage.
- Gives future features a common domain model.

### Negative / trade-offs

- Requires durable Trip and TripRevision persistence.
- Requires canonical place and provenance modeling.
- Adds explicit review steps instead of always optimizing for one-click generation.
- Increases contract and migration discipline.
- Delays lower-value features such as public feeds, marketplace search, and decorative AI chat.

## Alternatives considered

### Continue as an AI itinerary generator

Rejected because it is easy to replicate and does not leverage the project’s
existing readiness, evidence, and deterministic planning strengths.

### Become an OTA or booking marketplace

Rejected for the current stage because inventory, pricing, payments, and commercial
data access would dominate the engineering scope.

### Focus only on route optimization

Rejected as the sole product identity because optimization does not solve source
collection, identity resolution, provenance, collaboration, or dynamic repair.

## Related documents

- `docs/product/PRODUCT_DIRECTION.md`
- `docs/product/CODEX_AI_TRAVEL_PLANNER_PRODUCT_SPEC.md`
- `docs/research/AI_TRAVEL_PLANNER_PRODUCT_RESEARCH_2026-07-12.docx`

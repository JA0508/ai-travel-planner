# Product Direction

## Product identity

This repository is building a **Source-to-Executable Trip Workspace**.

The product converts fragmented travel inputs—guides, screenshots, copied text,
personal preferences, time boundaries, fixed reservations, and verified provider
facts—into a trip plan that is:

- explainable
- constraint-safe
- source-traceable
- reviewable
- versioned
- collaboratively editable
- dynamically repairable

A concise internal name is:

> **AI Trip Compiler / Executable Trip Workspace**

This project must not drift back into a generic “AI itinerary generator”, chat
wrapper, or map demo.

---

## Core user problem

Travelers rarely begin from a clean prompt. They usually already have:

- articles and social-media guides
- screenshots
- saved places
- group-chat suggestions
- restaurant or activity reservations
- arrival and departure times
- accessibility, pace, budget, or transport preferences
- incomplete and sometimes conflicting information

The product’s job is not merely to generate a plausible list of places.

Its job is to **compile messy travel intent and evidence into a plan that a user
can actually follow**, while making uncertainty, trade-offs, and repair actions
visible.

---

## Product promise

The product should answer five questions clearly:

1. **What did the system understand from my sources and request?**
2. **Which constraints are hard, soft, assumed, or unresolved?**
3. **Can this itinerary realistically be followed?**
4. **Why is each place and route segment arranged this way?**
5. **When something changes, what is the smallest safe repair?**

---

## Product moat

### 1. Source provenance

Every important place, constraint, and operational fact should be traceable to:

- a user input
- an imported source
- a booking
- a map/provider response
- a deterministic calculation
- a clearly labeled heuristic

The interface must not present heuristics or stale facts as confirmed truth.

### 2. Constraint compilation

Natural language is compiled into explicit structured fields:

- hard constraints
- soft preferences
- assumptions
- unresolved questions

LLMs may interpret these fields, but deterministic validation owns dates, time
windows, identity, permissions, and scheduling safety.

### 3. Executability

A plan is not “good” merely because it looks coherent.

The system should evaluate:

- fixed events
- arrival and departure boundaries
- availability windows
- route feasibility
- schedule slack
- place-data confidence
- missing or stale operational facts
- readiness for real execution

### 4. Revision-based change

The durable unit of product change is not a chat message. It is a **Trip Revision**.

Every import confirmation, drag-and-drop edit, AI adjustment, optimization, group
decision, and disruption repair should eventually become a structured patch
against a base revision.

This enables:

- impact preview
- stale-version protection
- change history
- comparison
- undo
- deterministic replay
- collaboration conflict handling

### 5. Explainable repair

When a trip changes, the product should prefer:

> **minimal, constraint-preserving, reviewable patches**

over full itinerary regeneration.

The system must show:

- what will change
- what will remain protected
- which facts are confirmed
- which effects are estimated
- whether the proposal can be safely applied
- how to undo it

### 6. Reproducible quality

The project should be able to replay planning runs using:

- structured intent
- provider snapshots
- planner version
- prompt version
- revision ID
- deterministic fixtures

CI should measure invariants and regressions, not only whether the code builds.

---

## Architecture boundary

### LLM responsibilities

LLMs may:

- interpret natural-language requests
- extract entities, preferences, and constraints
- classify hard/soft/assumed information
- propose candidates
- summarize sources
- explain deterministic results
- draft schema-valid patches
- identify ambiguity

LLMs must not:

- directly overwrite final itinerary state
- invent route times, opening hours, or booking facts
- silently choose ambiguous place identities
- move fixed events without explicit authorization
- claim execution succeeded before deterministic application completes

### Deterministic responsibilities

Deterministic systems own:

- canonical place identity
- geocoding and provider IDs
- date and time arithmetic
- fixed events
- availability windows
- arrival/departure boundaries
- route calculations
- validation
- scheduling
- patch application
- revision creation
- permissions
- idempotency
- stale-version detection
- fact freshness and conflict rules

Required flow:

```text
Source or user request
→ structured interpretation
→ schema validation
→ deterministic validation
→ impact preview
→ explicit confirmation
→ deterministic execution
→ new TripRevision
→ refreshed readiness and evidence
```

---

## Canonical domain direction

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

Important distinctions:

- `CanonicalPlace` is separate from `ScheduledItem`.
- `TripRevision` is the durable saved state.
- `PatchLog` is the unit of change.
- `Booking`, `TripLeg`, and `FixedEvent` are boundary objects.
- `PlaceFact` supports provenance, freshness, and conflicts.
- `ActualVisit` is separate from the planned itinerary.

---

## Current product strengths

The existing project already provides a meaningful foundation:

- natural-language intent parsing
- deterministic scheduling
- fixed-event and availability handling
- Completion Intelligence
- Planner Realism
- Trip Readiness
- map and timeline workspace
- Place Intelligence
- source/evidence-oriented UI
- route-aware editing
- impact-preview patterns
- provider fallback and request observability
- persisted TripRevision and server-authoritative mutation foundations
- text, URL, image, PDF, and layout-aware document import review foundations

These strengths should be preserved while the product expands upstream into
source import and downstream into revision-based execution.

---

## Current priority

The current next product objective is:

# F-004 Intent Compiler

The import stack can now produce reviewed mentions and TripCandidates from text,
URL, image, and document sources. The next product step is to compile reviewed
source facts into planner-ready intent:

- hard constraints
- soft preferences
- assumptions
- unresolved questions
- source-linked TripIntentEnvelope inputs

The recommended supporting follow-up is:

# F-020b Planner Trace Review and Evaluation Expansion

F-020b should strengthen evaluation, reviewer visibility, and regression
coverage around the compiler and planner path. It should not block the next
Import-to-Executable vertical slice unless current code, schemas, or tests reveal
a concrete safety issue.

The first strong vertical demo should be:

```text
Paste a guide or upload a screenshot
→ extract places and constraints
→ review ambiguous mentions
→ confirm canonical places
→ compile hard/soft/assumed intent
→ generate an executable plan
→ inspect readiness and place evidence
→ apply minimal repairs
→ export a traceable itinerary
```

---

## Non-goals for the current stage

Do not prioritize:

- full flight/hotel marketplace search
- payment or OTA functionality
- public travel social feeds
- unbounded recommendation content
- black-box global optimization
- full real-time disruption infrastructure before fixture validation
- heavy collaboration before TripRevision and permissions exist
- decorative AI chat experiences
- large UI rewrites without characterization tests

---

## Quality bar

A feature is not complete merely because it renders.

It must have, when relevant:

- explicit contracts
- clear state ownership
- deterministic validation
- loading/empty/partial/error/stale states
- failure recovery
- provenance and uncertainty semantics
- tests for hard constraints
- CI-equivalent verification
- honest limitations
- reviewable Git history

The project should become more intelligent without becoming less trustworthy.

---

## Canonical references

Authority order:

```text
code / schemas / tests
→ ADRs
→ CURRENT_PHASE
→ PRODUCT_DIRECTION
→ CODEX product specification
→ research snapshots
```

- `docs/product/CODEX_AI_TRAVEL_PLANNER_PRODUCT_SPEC.md`
- `docs/research/AI旅行规划产品深度研究_竞品UI与功能蓝图_2026-07-12.docx`
- `docs/decisions/0001-source-to-executable-trip-workspace.md`

The Markdown product specification is a planning and implementation reference.
The DOCX report is a dated human-facing research snapshot. Neither may override
current code, schemas, tests, ADRs, or `CURRENT_PHASE.md`.

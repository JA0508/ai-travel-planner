# Current Product Phase

## Current phase

F-001c Draft Trip and Pre-Plan Intent Workspace — in progress.

## Recently completed and merged

- F-002d Layout-Aware OCR and Document Text Extraction
- F-002d.1 Page-Level Extraction, Reading Order and Visual Evidence Hardening
- Product Direction and Roadmap Reconciliation
- F-004a Source-Linked Intent Contract Foundation
- F-004a.1 Typed Intent, Provenance and Concurrency Hardening
- F-004a.2 Semantic Intent Contract, Provenance Graph and Atomic Revision Closure
- F-004a.3 Completion Integrity Repair
- F-004b Planner Intent Handoff

The completed document extraction path now supports:

- inspection-gated image/PDF extraction
- native-text-first PDF extraction with page-level quality assessment
- selective local OCR for images and PDF pages that require rendering
- sanitized image and rendered-page preview provenance
- persisted page extraction records
- page-level retry with base-generation lineage
- layout blocks, lines, tokens, deterministic reading-order metadata, and span
  maps
- mention evidence linked to page and normalized bounding boxes
- existing Import Review Inbox reuse
- import evaluation gates for text, URL, binary, and document extraction

## Current stable capabilities

- Deterministic scheduler
- Trip Readiness
- Place Intelligence
- Route workspace
- Completion Intelligence
- constraint-preserving conversational replanning
- impact preview and before/after change review
- session undo
- reproducible frontend/backend CI
- F-006 Route Workspace Architecture Decomposition
- Source-to-Executable Governance Baseline
- F-020a Planner Trace and Deterministic Evaluation Baseline
- F-001a Trip + TripRevision Persistence Foundation
- F-001b persisted server-authoritative replan
- F-001b.1 Persisted Replan Proposal Integrity and Safe Undo Gate
- F-001b.2 Typed Route Edit and Swap Mutation Revisions
- F-001b.3 Candidate Admission, Completion Undo, and Mutation Closure
- F-002a Text Import and Import Review Inbox
- F-002b Secure URL Import Adapter
- F-002c Image/PDF Artifact Intake and Safe Document Classification
- F-002d Layout-Aware OCR and Document Text Extraction
- F-002d.1 Page-Level Extraction, Reading Order and Visual Evidence Hardening
- F-004a Source-Linked Intent Contract Foundation
- F-004a.1 Typed Intent, Provenance and Concurrency Hardening
- F-004a.2 Semantic Intent Contract, Provenance Graph and Atomic Revision Closure
- F-004a.3 Completion Integrity Repair
- F-004b Planner Intent Handoff

## Known technical debt

- The document extraction evaluation corpus currently has 5 document fixtures.
- Advanced multi-column reading-order reconstruction remains limited.
- Five-viewport layout-aware browser visual smoke coverage is incomplete.
- Local OCR behavior is intentionally capability-reported and may vary by
  installed language packs and rendering dependencies.
- F-004a.3 Completion Integrity Repair is merged. It persists verified
  candidate-to-import lineage, fails closed for legacy-unverified candidates,
  exercises real immutable revision and SQLite race scenarios, and hands
  provenance nodes back to the existing private Import Review workspace.
- F-004b is merged. It introduces a narrow, server-authoritative handoff
  from the latest verified `TripIntentEnvelope` to a frozen deterministic
  planner preview and an atomic apply operation. It is not a full planner trace
  review workspace, provider-refresh system, or multi-city planner.
- A fixed event without a verified canonical TripCandidate is deliberately
  blocked at handoff rather than geocoded from free-form location text.
- F-004b currently supports one destination per handoff. Multi-destination
  intents remain explicit, planner-blocking product work rather than a silent
  fallback to a single city.
- Provenance graph navigation opens the existing private Import Review workspace
  for an import job/page when structured evidence supplies that identity. It is
  not yet a full Planner Trace review workspace.
- The intent compiler evaluation corpus now has 63 fixtures and CI gates fixture
  counts plus deterministic invariants across semantic, provenance, parser,
  revision, concurrency, and clarification categories. It should still expand
  when F-004b introduces planner handoff behavior.
- F-004a.3 records privacy-safe compile run metadata for parser/compiler policy,
  readiness policy, semantic digest, lineage digest, and idempotency lineage. It
  intentionally does not persist raw prompts, raw LLM responses, private source
  text, or planner traces.

## Current next product objective

1. F-001c Draft Trip and Pre-Plan Intent Workspace

The active product step makes the admission sequence explicit: a private Draft
Trip can persist reviewed sources and an immutable pre-plan intent contract
without fabricating an empty itinerary revision. The first deterministic planner
handoff remains a frozen preview and, on confirmation, atomically creates
`TripRevision` 1.

Current F-001c work includes:

- private Draft Trip lifecycle distinct from an executable trip
- immutable draft intent contracts with a null itinerary-revision baseline
- reviewable source candidate selection before compiler input
- private source-text recovery after browser reload using the existing capability
  boundary
- frozen pre-plan planner runs with stale-intent rejection and idempotent apply

F-001c does not yet replace all legacy structured-form generation paths or add
full draft editing/history UX. Those remain explicit follow-up work; they must
not silently bypass the pre-plan contract boundary.

F-004b remains the post-revision handoff for an already saved itinerary and
continues to hand the confirmed `TripIntentEnvelope` to planner input preparation
without weakening the contract boundary:

- hard constraints
- soft preferences
- assumptions
- unresolved questions
- planner-ready intent preview
- structured source evidence summaries and provenance graph edges
- confirmed domain-native fields
- semantic digest and lineage ownership

F-004b stores a privacy-safe, immutable planner handoff run and frozen proposal
before an explicit apply creates the next `TripRevision`. Apply compares both
the base TripRevision and latest IntentRevision in the same SQLite transaction;
it never reruns the planner. LLM explanations cannot override user edits,
reviewed evidence, fixed events, availability windows, or deterministic
readiness policy.

## Supporting follow-up

1. F-020b Planner Trace Review and Evaluation Expansion

F-020b should expand planner trace review and evaluation coverage, especially
around source-to-intent compilation and planner regression gates. It is a
supporting quality objective, not a replacement for the Import-to-Executable
product closure.

## Explicitly not in scope for the next step

- OTA marketplace search
- payment or booking modification
- public travel content communities
- generic recommendation feeds
- direct document-to-itinerary mutation
- collaboration
- Booking inbox

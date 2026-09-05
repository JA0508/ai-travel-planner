# Current Product Phase

## Current phase

Round 29 Real-Life Rhythm / Meal Windows — implemented on
`codex/meal-rhythm-v1` and awaiting Draft PR review. It is not merged yet.

## Recently completed and merged

- F-002d Layout-Aware OCR and Document Text Extraction
- F-002d.1 Page-Level Extraction, Reading Order and Visual Evidence Hardening
- Product Direction and Roadmap Reconciliation
- F-004a Source-Linked Intent Contract Foundation
- F-004a.1 Typed Intent, Provenance and Concurrency Hardening
- F-004a.2 Semantic Intent Contract, Provenance Graph and Atomic Revision Closure
- F-004a.3 Completion Integrity Repair
- F-004b Planner Intent Handoff
- Round 27 Controlled Local Repair UX
- Round 28 Safe Replace
- Round 28.1 Replace Candidate Quality Gate

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

## Recently recorded locally (not merged)

- Import Full-Format Release Batch 05 runbook/release-record closure (browser gate rerun is environment-limited; not an external deployment)

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
- Living Roadbook route-first saved workspace
- server-authoritative local relaxation preview/apply/undo
- verified Safe Replace preview/apply/undo with candidate quality gates

## Known technical debt

- The document extraction evaluation corpus currently has 5 document fixtures.
- Advanced multi-column reading-order reconstruction remains limited.
- Five-viewport layout-aware browser visual smoke coverage is incomplete.
- Local OCR behavior is intentionally capability-reported and may vary by
  installed language packs and rendering dependencies.
- Import Full-Format Release 的 API/evaluation gate 已通过 68/68 local fixtures 与 8/8
  gate cases；Batch 05 已新增浏览器 gate/runbook/release record，但 2026-09-03 当前
  Codex 沙箱重跑在 fixture backend 绑定 `127.0.0.1:8030` 时被环境拒绝。因此本文不把
  Text/URL browser closure、binary upload/OCR 或 PDF extraction 声称为已验证；详见
  `docs/architecture/IMPORT_FULL_FORMAT_RELEASE_RECORD_2026-09-03.md`。
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

1. Complete the Round 29 release gate and review its Draft PR.

Round 29 adds deterministic lunch/dinner applicability, conservative existing
meal recognition, verified and route-safe meal completion, explicit Meal Gap
results, frozen Planning Run evidence, TripRevision continuity, and Living
Roadbook presentation. It does not add a dining recommendation engine or a new
planning workflow.

After Round 29 is accepted, the next product objective is Confirmation UX P0.
It replaces the Draft Intent confirmation page's repeated blocker forms with a
single, source-aware confirmation queue while preserving verified-place,
fixed-event and revision boundaries. The implementation plan is
`tasks/confirmation-ux-p0-plan.md`.

Opening-Hours Temporal Feasibility follows Confirmation UX P0: verify that a
place is operational during its scheduled visit rather than claiming more than
route and time-window evidence proves.

Known Round 29 boundaries remain explicit:

- V1 supports lunch and dinner only.
- Default windows are 11:30-14:00 and 17:30-20:30.
- User-configurable meal windows are not yet part of the Intent Contract.
- Opening hours, live queues, bookings, ratings, and restaurant ranking are not
  part of meal feasibility.

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

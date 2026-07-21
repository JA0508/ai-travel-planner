# Current Product Phase

## Current phase

Product Direction and Roadmap Reconciliation after F-002d / F-002d.1.

## Recently completed and merged

- F-002d Layout-Aware OCR and Document Text Extraction
- F-002d.1 Page-Level Extraction, Reading Order and Visual Evidence Hardening

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

## Known technical debt

- The document extraction evaluation corpus currently has 5 document fixtures.
- Advanced multi-column reading-order reconstruction remains limited.
- Five-viewport layout-aware browser visual smoke coverage is incomplete.
- Local OCR behavior is intentionally capability-reported and may vary by
  installed language packs and rendering dependencies.
- Import Review can produce reviewed mentions and TripCandidates, but reviewed
  source facts are not yet compiled into a planner-ready TripIntentEnvelope.

## Current next product objective

1. F-004 Intent Compiler

The next product step is to compile reviewed source facts into:

- hard constraints
- soft preferences
- assumptions
- unresolved questions
- planner-ready intent

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

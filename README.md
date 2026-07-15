# AI Travel Planner

> **Source-to-Executable Trip Workspace**
> Compile guides, screenshots, preferences, time boundaries, fixed reservations,
> and verified place facts into an explainable, constraint-safe, executable trip.

<!--
Optional badges can be added after CI is stable.

Example:
Frontend CI badge
Backend CI badge
-->

## Overview

AI Travel Planner is a full-stack travel planning system built around a strict
separation of responsibilities:

- **LLMs understand, classify, propose, summarize, and explain.**
- **Deterministic systems resolve, validate, schedule, version, and execute.**

The project is intentionally different from generic “prompt in, itinerary out”
travel demos.

Its long-term product direction is a **Source-to-Executable Trip Workspace**:
users should be able to bring fragmented travel material into the system, review
what was extracted, confirm places and constraints, generate a realistic route,
understand why it was arranged that way, and apply safe, reversible repairs when
the trip changes.

---

## Product vision

```text
Guides / screenshots / notes / bookings / preferences
                         ↓
                  Source extraction
                         ↓
             Place and constraint review
                         ↓
                 Intent compilation
                         ↓
              Deterministic planning
                         ↓
        Readiness + route + place evidence
                         ↓
          Versioned patches and safe repair
                         ↓
                  Executable trip
```

The core product object is not a chat transcript. It is a **versioned trip** with
traceable sources, protected constraints, and reviewable revisions.

---

## Why this project is different

### Constraint-safe planning

Fixed events, availability windows, arrival/departure boundaries, and explicit
user protections are treated as first-class planning constraints.

### Explainable execution

The system does not only show where to go. It surfaces:

- readiness state
- primary risks
- protected boundaries
- route context
- place fit
- supporting evidence
- missing or uncertain data

### Place Intelligence

Place details are structured around:

- identity
- trust
- route fit
- visit context
- caveats
- evidence
- available actions

### Repair instead of silent regeneration

The product direction favors structured patches:

```text
interpretation
→ constraint check
→ impact preview
→ confirmation
→ deterministic execution
→ before/after review
→ undo
```

### Source-to-plan compilation

The next major product line is **Import-to-Executable v1**:

- import text, screenshots, URLs, and documents
- review extracted mentions
- resolve canonical places
- compile hard/soft/assumed constraints
- generate a deterministic plan
- preserve provenance through execution

---

## Current capabilities

The repository currently contains a substantial planning foundation:

- natural-language trip intent parsing
- structured planning-state parsing
- deterministic multi-day scheduling
- morning / afternoon / evening blocks
- fixed day and fixed time handling
- flexible availability windows
- optional hotel-anchor planning
- route-aware POI ordering
- Completion Intelligence
- Planner Realism analysis
- Trip Readiness
- desktop map/timeline workspace
- mobile route-editing workspace
- Day layers and route controls
- Place Intelligence and evidence presentation
- provider fallback behavior
- request IDs and process-time observability
- idempotency support for selected mutation paths
- persisted replan proposal preview/apply integrity
- typed route edit and swap mutation proposals
- immutable route-edit/swap revisions with compensating undo
- persisted TripCandidate intake and workflow decisions
- typed candidate admission with repair-required semantics
- saved completion undo as a compensating TripRevision
- fixture-driven product verification

> Development branches may contain additional in-review capabilities. Required CI
> checks must be green before those capabilities are considered part of the stable
> baseline.

---

## Product interface

### Result workspace

The desktop result experience follows a stable decision-workspace structure:

```text
┌─────────────────────────────────────────────────────────────────────┐
│ Trip Readiness │ Route Map and Controls │ Timeline / Place Detail  │
└─────────────────────────────────────────────────────────────────────┘
```

- **Left:** readiness, primary issues, protected boundaries, next actions
- **Center:** route map, Day layers, selected stop, route context
- **Right:** Day timeline or Place Intelligence

### Screenshot placeholders

#### Desktop workspace

> **Screenshot placeholder:** desktop three-column trip workspace
> Suggested file: `docs/assets/desktop-trip-workspace.png`

#### Place Intelligence

> **Screenshot placeholder:** place trust, route fit, caveats, and evidence
> Suggested file: `docs/assets/place-intelligence.png`

#### Mobile route workspace

> **Screenshot placeholder:** mobile map + timeline/bottom-sheet workflow
> Suggested file: `docs/assets/mobile-route-workspace.png`

#### Constraint-preserving adjustment flow

> **Screenshot placeholder:** interpretation → impact preview → change review
> Suggested file: `docs/assets/replanning-flow.png`

---

## Architecture

```text
Frontend
  Next.js App Router + TypeScript
        │
        │ typed JSON contracts
        ▼
Backend
  FastAPI + Pydantic
        │
        ├── LLM interaction services
        │     intent parsing
        │     ambiguity detection
        │     explanation
        │
        ├── Deterministic planning services
        │     constraint validation
        │     scheduling
        │     readiness
        │     patch application
        │
        └── Provider adapters
              geocoding
              POI lookup
              route preview
              stay/departure context
```

### Required architecture boundary

LLMs must not directly overwrite final itinerary state.

The safe execution path is:

```text
natural-language request
→ schema-valid interpretation
→ deterministic validation
→ impact preview
→ confirmed execution
→ refreshed itinerary surfaces
```

---

## Tech stack

### Frontend

- Next.js
- React
- TypeScript
- App Router
- browser-side Amap integration
- typed view-model and fixture-driven UI patterns

### Backend

- FastAPI
- Pydantic
- Python
- modular API / schema / service / core structure
- deterministic scheduler
- Amap provider integrations
- OpenAI-compatible intent and disambiguation layer

### Infrastructure and quality

- GitHub Actions
- frontend type checking and production build
- backend unit/integration tests
- request IDs
- process-time headers
- provider-readiness endpoint
- idempotency on supported operations

---

## Repository structure

```text
.
├── backend/                 FastAPI application and deterministic services
├── frontend/                Next.js application
├── infra/                   deployment and infrastructure configuration
├── skills/                  project-local agent skills
├── docs/
│   ├── product/             canonical product direction and implementation spec
│   ├── research/            dated product and competitor research
│   ├── decisions/           architecture decision records
│   └── assets/              README and documentation images
├── .github/                 CI workflows
├── AGENTS.md                coding-agent operating rules
└── README.md
```

---

## Local setup

### Prerequisites

- Node.js compatible with the repository lockfile and CI
- npm
- Python compatible with the backend test environment
- an isolated Python virtual environment

### 1. Clone and enter the repository

```bash
git clone <repository-url>
cd ai-travel-planner
```

### 2. Configure the backend

```bash
cp backend/.env.example backend/.env
```

Important backend settings include:

- `APP_ENV`
- `POI_DISCOVERY_MODE`
- `CORS_ALLOW_ORIGINS`
- `AMAP_API_KEY`
- `AMAP_REQUEST_TIMEOUT_SECONDS`
- `OPENAI_API_KEY`
- `OPENAI_INTENT_MODEL`
- `OPENAI_INTENT_TIMEOUT_SECONDS`
- `OPENAI_DISAMBIGUATION_TIMEOUT_SECONDS`
- `LOG_LEVEL`
- `TRIP_STORE_MODE`
- `TRIP_STORE_PATH`
- `TRIP_STORE_BUSY_TIMEOUT_SECONDS`
- `TRIP_CAPABILITY_COOKIE_SECURE`
- `TRIP_ALLOWED_ORIGINS`

Do not commit `backend/.env`.

Development can run with fallback POI discovery when provider credentials are not
available. Production should use explicit provider configuration and strict
readiness behavior.

TripRevision persistence defaults to SQLite in development. Local database,
WAL, and SHM files are ignored by Git. The backend stores only a hash of the
anonymous trip capability and sends the raw capability in an HttpOnly,
SameSite=Strict cookie. The browser stores only `{schemaVersion, tripId,
currentRevisionId}` in localStorage, never the capability or the full itinerary.

Anonymous capability access protects private trip URLs from casual reads, but it
is not a substitute for account authentication, formal authorization, or
multi-user permissions.

### 3. Configure the frontend

```bash
cp frontend/.env.example frontend/.env.local
```

Important frontend settings include:

- `NEXT_PUBLIC_API_BASE_URL`
- `NEXT_PUBLIC_AMAP_WEB_KEY`
- `NEXT_PUBLIC_AMAP_SECURITY_JS_CODE`

Without a browser-side Amap key, the application should degrade to its supported
list-first/fallback experience rather than failing the entire workspace.

### 4. Install dependencies

```bash
cd frontend
npm ci
```

```bash
cd ../backend
python -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

### 5. Run the backend

From `backend/` with the virtual environment activated:

```bash
python -m uvicorn app.main:app --reload --port 8000
```

Backend readiness:

```text
GET http://localhost:8000/readiness
```

### 6. Run the frontend

In a second terminal:

```bash
cd frontend
npm run dev
```

Open:

```text
http://localhost:3000
```

---

## Verification

Run clean, reproducible checks before marking a feature ready for review.

### Frontend

```bash
cd frontend
npm ci
npm run typecheck
npm run test:workspace
npm run build
```

`npm run test:workspace` covers the route workspace characterization tests and
Trip persistence state/storage helpers.

### Backend

From the repository root:

```bash
backend/.venv/bin/python -m unittest discover -s backend/tests -t backend
backend/.venv/bin/python -m tools.run_planner_evaluation --ci
backend/.venv/bin/python -m tools.run_trip_mutation_evaluation --ci
```

Or, with the backend virtual environment activated:

```bash
cd backend
python -m pytest
```

### Git hygiene

```bash
git diff --check
git status --short
```

A feature is not ready for review while required GitHub Actions checks are failing.

---

## Runtime behavior and resilience

### Provider fallback

When Amap credentials are unavailable in an allowed development/fallback mode:

- the backend remains runnable
- provider-backed discovery may degrade
- curated fallback candidates may be used
- the UI must not claim provider-confirmed facts

In production-required mode, missing provider credentials should fail readiness or
startup according to the backend configuration.

### Observability

Backend responses expose:

- `X-Request-ID`
- `X-Process-Time-Ms`

The frontend sends request IDs for JSON API operations.

Supported mutation paths may use `X-Idempotency-Key` to prevent duplicate execution.

Persisted TripRevision write endpoints require `X-Idempotency-Key`. Safe retry is
resolved before stale-base validation so a lost response can be retried without
creating a duplicate revision.

Persisted conversational replan uses a two-step proposal contract:

```text
preview follow-up text -> persisted TripMutationProposal -> apply proposal digest
```

Apply does not receive raw follow-up text and does not rerun the planner. The
server validates proposal lifecycle, expiry, base revision, digest integrity, and
stored preview content before creating the immutable `TripRevision`.

Route edit and swap use the same proposal/apply infrastructure with typed
commands instead of arbitrary itinerary uploads:

```text
POST /trips/{trip_id}/mutations/preview
POST /trips/{trip_id}/mutation-proposals/{proposal_id}/apply
```

The command schema is versioned (`1.0`) and targets stable scheduled-item IDs.
The backend deterministic mutation engine computes the preview snapshot,
command digest, impact summary, and invalidated derived surfaces. Apply validates
the persisted proposal and creates the revision without rerunning the engine,
planner, geocoder, or route provider.

Candidate handling is split from executable itinerary mutation. Candidate intake,
reject, defer, and restore are persisted workflow decisions and do not create
`TripRevision` records. A candidate becomes itinerary state only through a typed
candidate-admission proposal:

```text
POST /trips/{trip_id}/candidates
POST /trips/{trip_id}/candidates/{candidate_id}/decisions
POST /trips/{trip_id}/mutations/preview
POST /trips/{trip_id}/mutation-proposals/{proposal_id}/apply
```

Admission commands reference a server-owned `candidate_id` and target slot. The
backend validates candidate workflow state, required execution facts, schedule
invariants, proposal digest, base revision, and idempotency before creating an
immutable revision. Missing execution facts return repair-required state instead
of silently scheduling weak or invented data.

Saved completion undo is also server-authoritative: undoing a persisted
completion patch creates a compensating revision and preserves lineage instead
of treating the browser as the canonical saved state.

### Uncertainty semantics

The product distinguishes:

- provider facts
- user constraints
- deterministic calculations
- heuristics
- missing data

Missing or stale data must not be presented as confirmed.

---

## Product roadmap

### Foundation

- reproducible CI
- characterization fixtures
- page-level orchestration decomposition
- Trip and TripRevision persistence
- planner trace and deterministic evaluation corpus
- persisted mutation proposal integrity for conversational replan
- typed route edit and swap mutation revisions

### Import-to-Executable v1

- Universal Import
- Import Review Inbox
- canonical POI resolution
- Trip Intent Compiler
- explainable planner trace
- source and freshness-aware Place Intelligence
- explainable route optimization
- read-only sharing and export

### Later product layers

- collaboration and permissions
- booking/document inbox
- multi-city trip boundaries
- during-trip mode and offline pack
- disruption repair
- place library and collections
- planned-versus-actual recap

See:

- `docs/product/PRODUCT_DIRECTION.md`
- `docs/product/CODEX_AI_TRAVEL_PLANNER_PRODUCT_SPEC.md`

---

## Engineering principles

- LLMs interpret and propose; deterministic systems validate and execute.
- Fixed events and hard boundaries must not be silently changed.
- Prefer patches over full itinerary rewrites.
- Unknown data is not equivalent to zero or safe.
- Real-world facts require provenance and freshness.
- Do not expand `frontend/src/app/page.tsx`.
- Do not duplicate scheduler, patch, constraint, or diff logic.
- Build reviewable vertical slices.
- Preserve rollback, idempotency, and stale-version safety.
- Keep UI claims aligned with evidence strength.
- Keep `main` releasable and CI green.

Agent-specific rules are defined in `AGENTS.md`.

---

## Known limitations

The project is still evolving from a strong planning prototype into a durable trip
workspace.

Current limitations include:

- no production-grade user authentication and multi-user persistence
- TripRevision persistence is local SQLite, not a cloud Trip Library
- limited source-import pipeline
- incomplete canonical place/provenance graph
- Completion Undo, manual pending-stop insertion, and selected candidate-reject
  workflows remain to be classified or migrated
- no full booking inbox
- no production disruption-monitoring infrastructure
- no offline travel pack
- no OTA search, payment, or booking modification
- provider coverage depends on configuration and availability
- some advanced mutation capabilities may remain branch-specific or under review

These limitations are intentionally visible rather than hidden behind generated copy.

---

## Security and privacy

Travel plans, locations, bookings, and uploaded artifacts should be treated as private.

- never commit real API keys
- keep `.env` files out of Git
- redact sensitive fixture and log data
- validate uploaded files before processing
- protect URL fetching from SSRF
- do not expose provider credentials to the browser unless they are explicitly
  browser-safe public configuration values
- default future trip sharing and collaboration features to least privilege

---

## Documentation

- Product direction: `docs/product/PRODUCT_DIRECTION.md`
- Full implementation specification:
  `docs/product/CODEX_AI_TRAVEL_PLANNER_PRODUCT_SPEC.md`
- Research snapshot:
  `docs/research/AI_TRAVEL_PLANNER_PRODUCT_RESEARCH_2026-07-12.docx`
- Architecture decisions: `docs/decisions/`

The Markdown product specification is the canonical engineering reference.
The DOCX report is a dated human-facing research artifact.

---

## Project status

This repository is under active product development.

Changes should move the system toward an explainable, versioned, source-aware,
constraint-safe trip workspace—not toward a generic AI chat experience.

# AGENTS.md

## 1. Repository mission

This repository implements a **Source-to-Executable Trip Workspace**.

The product converts fragmented travel inputs—guides, screenshots, notes, preferences,
time boundaries, fixed reservations, and provider facts—into an itinerary that is:

- explainable
- constraint-safe
- source-traceable
- reviewable
- versioned
- collaboratively editable
- dynamically repairable

This is not a generic “AI itinerary generator”, a chat wrapper, or a visual demo.
Every change should strengthen the compilation path from source material to an
executable trip.

---

## 2. Instruction precedence

When instructions conflict, use this order:

1. The current user task
2. This `AGENTS.md`
3. `docs/product/PRODUCT_DIRECTION.md`
4. The explicitly referenced F-xxx sections in
   `docs/product/CODEX_AI_TRAVEL_PLANNER_PRODUCT_SPEC.md`
5. Existing repository code, schemas, tests, and API behavior
6. Other research or reference documents

Repository code and tests describe the current implementation truth.
Product documents describe intended direction. If they disagree, do not silently
choose one: report the mismatch and implement only the explicitly authorized scope.

The DOCX research report under `docs/research/` is a human-facing research snapshot.
It is not the canonical implementation contract.

---

## 3. Required reading before implementation

For every non-trivial task:

1. Read this file.
2. Read `docs/product/PRODUCT_DIRECTION.md`.
3. Read only the F-xxx sections explicitly named in the task.
4. Inspect the real entry points, schemas, services, state owners, and tests involved.
5. Check the current Git branch, working tree, and recent commits.
6. Identify the smallest coherent vertical slice that satisfies the task.
7. Proceed with implementation unless the task is explicitly analysis-only.

Do not implement adjacent roadmap items merely because they appear in the product spec.

---

## 4. Core architecture boundary

### LLM layer

LLMs may:

- interpret natural-language requests
- extract entities, preferences, and constraints
- classify hard constraints, soft preferences, and assumptions
- propose candidates
- summarize evidence
- explain deterministic results
- draft schema-valid patches
- identify ambiguity and request clarification

LLMs must not:

- directly overwrite the final itinerary
- invent provider facts
- calculate authoritative route times or distances
- bypass fixed events or time boundaries
- silently resolve ambiguous place identity
- claim that a mutation was applied before deterministic execution succeeds

### Deterministic layer

Deterministic systems own:

- canonical place identity
- geocoding and provider IDs
- date and time calculations
- fixed events and availability windows
- arrival and departure boundaries
- route lookup and route metrics
- validation
- scheduling
- patch application
- revision creation
- permissions
- idempotency
- stale-version detection
- fact freshness and conflict rules

The required flow is:

```text
source or user request
→ structured interpretation
→ schema validation
→ deterministic validation
→ impact preview
→ explicit confirmation when destructive
→ deterministic execution
→ new TripRevision
→ readiness and evidence refresh
```

---

## 5. Product invariants

These rules must not be violated unless the current task explicitly changes them:

- Fixed events remain fixed unless the user explicitly authorizes a change.
- Availability windows and arrival/departure boundaries are hard constraints.
- Unknown data is not equivalent to safe, zero, or false.
- Missing route data must not be presented as confirmed travel time.
- Real-time or operational facts require source, observation time, and verification state.
- Ambiguous place mentions must not become canonical places without deterministic
  resolution or explicit user confirmation.
- A failed mutation must leave the current itinerary unchanged.
- Destructive edits require impact visibility and a recoverable path.
- Replanning should prefer patches over full itinerary rewrites.
- Each applied mutation should be attributable to a base revision.
- A stale patch or proposal must not be applied to a newer revision.
- The same idempotency key must not apply the same operation twice.
- Frontend presentation must not imply stronger certainty than backend evidence supports.

---

## 6. Canonical product model

The long-term product model is centered on:

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

- `CanonicalPlace` is not the same object as `ScheduledItem`.
- `TripRevision` is the durable saved state.
- `PatchLog` is the unit of change.
- `Booking`, `TripLeg`, and `FixedEvent` are boundary objects, not ordinary POIs.
- `PlaceFact` supports provenance, freshness, and conflicts.
- `ActualVisit` is separate from the planned itinerary.

Do not introduce duplicate domain models for the same concept in different features.

---

## 7. Repository structure

Expected top-level structure:

```text
backend/                 FastAPI application and deterministic services
frontend/                Next.js application
infra/                   deployment, container, and infrastructure configuration
docs/
  product/               canonical product direction and implementation specification
  research/              dated research snapshots and human-facing reports
  decisions/             architecture decision records
  assets/                documentation images and diagrams
skills/                  project-local skills used by coding agents
.github/                 CI and repository automation
AGENTS.md
README.md
```

Do not place `product/` or `research/` as separate top-level folders.
Do not leave temporary screenshots or exported documents in the repository root.

---

## 8. Scope and change discipline

- Prefer the smallest **coherent vertical slice**, not the smallest possible edit.
- Do not perform unrelated refactors.
- Do not rename public fields without an explicit migration plan.
- Preserve backward compatibility unless the task explicitly allows a breaking change.
- Cross-layer changes are allowed only when required by a real contract change.
- Do not create placeholder endpoints, fake buttons, or unsupported UI states.
- Do not duplicate an existing scheduler, constraint model, diff model, or patch engine.
- Avoid creating another page-scale component or service.
- New domains should have explicit types/schemas, pure logic, adapters, and tests.
- Remove dead code and obsolete branches created by the change.
- Document contract gaps instead of fabricating support.

For large refactors, first add characterization tests and then move behavior in
reviewable stages.

---

## 9. Frontend rules

### State ownership

Classify state before adding it:

- server state
- durable trip/revision state
- draft patch state
- selection state
- ephemeral UI state
- async operation state

A domain fact should have one owner. Do not mirror `activeDay`, `selectedStop`,
revision, or workflow status across unrelated components.

Prefer discriminated unions or reducers for multi-step workflows instead of many
interdependent booleans.

### Component boundaries

- Route files should compose screens, not contain domain logic.
- Containers coordinate data and mutations.
- View-models/selectors derive user-facing state.
- Presentational components render typed props.
- Pure domain calculations must not live inside JSX.
- Do not continue growing `frontend/src/app/page.tsx`.
- Feature code should live under `frontend/src/features/` or the repository’s
  established equivalent.

### UI quality

For UI work, first read:

`skills/web-design-engineer/SKILL.md`

The visual direction is **Editorial Cartography**:

- high information density with clear hierarchy
- map and timeline as working surfaces
- restrained typography, borders, spacing, and motion
- no generic AI gradients, glowing cards, badge walls, or decorative dashboards
- no fake precision scores
- no UI claim that exceeds available evidence

Responsive behavior must be designed for desktop, tablet, and mobile rather than
compressing the desktop layout.

Accessibility requirements include keyboard operation, visible focus, semantic
warnings, reduced motion, focus restoration, and no color-only meaning.

---

## 10. Backend rules

- Keep API route handlers thin.
- Put domain logic in services or domain modules.
- Use Pydantic schemas for external contracts.
- Validate LLM output before it enters deterministic services.
- Keep provider adapters separate from planning logic.
- Do not perform network calls inside pure evaluators.
- Reuse geocoding and route results when safe.
- Add explicit timeout, retry, fallback, and partial-data behavior.
- Return stable error codes for recoverable product states.
- Preserve request IDs and process-time observability.
- Do not log private itinerary text, documents, confirmation codes, or secrets.

Any new mutation path must address:

- base revision
- idempotency
- validation
- partial failure
- stale state
- rollback or undo semantics
- readiness and dependent-surface refresh

---

## 11. Facts, provenance, and uncertainty

Provider or imported facts should support, where applicable:

```text
source_type
source_ref
observed_at
expires_at
verification_status
confidence
conflict_group
```

Use these semantic classes consistently:

- provider fact
- user constraint
- deterministic calculation
- heuristic
- missing data

Heuristics must not be rendered as confirmed facts.
Expired facts must not use confirmed styling.
Conflicting facts should remain visible as conflicts rather than being silently merged.

---

## 12. External integrations

External APIs should increase correctness without becoming single points of failure.

For every provider integration:

- define timeout behavior
- define retry behavior
- define quota/rate-limit behavior
- define cache/reuse behavior
- define partial response handling
- define fallback semantics
- record provenance
- never expose credentials to the frontend or logs

Do not bypass access controls, login walls, robots restrictions, or provider terms.

---

## 13. Testing and verification

Do not claim completion based only on a local build.

Use the repository’s real commands and, where applicable, CI-equivalent clean
environments.

Minimum expectations for changed code:

- pure domain unit tests
- schema/contract tests
- integration tests for cross-layer changes
- at least one fixture-driven interaction or end-to-end verification for user workflows
- regression coverage for fixed boundaries and failure recovery
- `git diff --check`

Critical invariants to test when relevant:

- fixed events remain unchanged
- no overlapping scheduled items
- no duplicate mutation execution
- failed execution preserves the original itinerary
- undo restores dependent surfaces
- stale proposals are rejected
- missing data is not treated as zero
- deterministic inputs produce deterministic outputs
- secrets and PII do not appear in logs

If CI and local results differ, diagnose the environment difference before changing
business expectations.

---

## 14. Git and pull request rules

Before editing:

```bash
git branch --show-current
git status --short
git log --oneline --decorate -5
```

- Work on a task-specific branch unless explicitly told otherwise.
- Keep `main` releasable.
- Do not force-push unless explicitly authorized.
- Do not merge a PR automatically.
- Do not hide failing tests by weakening CI commands.
- Do not commit `.env`, credentials, caches, build output, virtual environments, or
  local machine files.
- Keep commits semantic and reviewable.
- Update the same feature branch when fixing its CI.
- Documentation-only changes should use a separate documentation branch/PR.

A feature is not ready for review while required CI checks are failing.

---

## 15. Security and privacy

Treat travel plans, locations, bookings, documents, and collaborator identities as
private data.

- Default new trips and artifacts to private.
- Use least-privilege access.
- Redact sensitive fields from logs, analytics, fixtures, and screenshots.
- Validate file type, size, and content before processing uploads.
- Protect URL fetching from SSRF and unsafe redirects.
- Do not store raw third-party content without a clear need and policy.
- Never commit real API keys or tokens.
- Use `.env.example` only for placeholders.

---

## 16. Documentation rules

Update documentation when a change affects:

- product behavior
- API contracts
- domain models
- setup or verification commands
- architecture decisions
- known limitations

Use an ADR under `docs/decisions/` for durable architectural decisions.

Do not duplicate the canonical product specification in multiple files.
The Markdown product spec is canonical; the DOCX research report is a dated export.

### Product document update policy

- `docs/product/PRODUCT_DIRECTION.md` is a stable product charter.
- Read it before non-trivial product work.
- Do not modify it for routine features, bug fixes, UI changes, or refactors.
- Modify it only when the current task explicitly changes long-term product identity,
  architectural boundaries, core domain concepts, or major product priorities.
- If implementation reveals a mismatch with the product direction, report the mismatch
  and propose a documentation change; do not silently rewrite the document.
- `docs/product/CURRENT_PHASE.md` may be updated when a milestone, active phase, or
  approved next step changes.
- Relevant F-xxx sections in the full product specification may be updated when actual
  implementation invalidates their contracts or acceptance criteria.
---

## 17. Completion report

For every completed task, return:

### Implemented
What was actually delivered.

### Product and architecture impact
Which product capability and architectural boundary changed.

### Files changed
Key files and their new responsibilities.

### Contract impact
API, schema, state, migration, and compatibility effects.

### Verification
Exact commands, test counts, and real outcomes.

### Risks and limitations
Known gaps, unsupported operations, and environment constraints.

### Git status
Branch, commits, working tree, push/PR state, and whether CI is green.

Do not describe planned, mocked, partial, or unverified behavior as complete.

---

## 18. Final operating rule

The product should become more intelligent without becoming less trustworthy.

Use LLMs to understand and propose.
Use deterministic systems to resolve, validate, version, and execute.
Preserve provenance, constraints, reversibility, and evidence at every step.

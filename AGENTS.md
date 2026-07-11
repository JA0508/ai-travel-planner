# AGENTS.md

## Project identity
This repository is an LLM-native, product-oriented full-stack travel itinerary planning system.

It is not a toy demo and should not be treated as one.
It should evolve as a maintainable product codebase with stable contracts, explicit behavior, resilient integrations, and disciplined iteration.

The product should combine:
- an LLM-driven interaction layer
- a deterministic execution layer

These two layers must work together, but they must not be conflated.

---

## Product direction
The long-term direction of this product is:

- natural-language trip planning
- preference-aware interaction
- explainable itinerary generation
- interest-first trip skeleton planning
- later-stage stay selection and stay-area recommendation
- conversational itinerary refinement
- continued product iteration without architecture drift
- support both fixed-duration and flexible-duration trip planning
- estimate a reasonable trip scope when user time is not fully specified
- treat time flexibility as a first-class input dimension, not just a missing trip_days field

The system should increasingly feel like an intelligent travel planning product, not just a form-based itinerary tool.

LLM capabilities are part of the active product direction.
They are not optional polish.

---

## System architecture concept

### 1. LLM interaction layer
This layer is responsible for:
- natural-language trip input
- intent parsing
- constraint extraction
- preference modeling
- candidate POI suggestion and cleanup
- user-facing explanation
- conversational replanning
- interaction flow improvement

This layer may interpret, organize, and explain user intent.

### 2. Deterministic execution layer
This layer is responsible for:
- geocoding
- route lookup
- fixed-constraint enforcement
- candidate ranking
- itinerary scheduling
- stable response generation
- execution-time validation

This layer must remain deterministic, explainable, and bounded by explicit logic.

### Boundary rule
The LLM layer must not replace deterministic execution logic.
The deterministic layer must not be forced to behave like an unconstrained generative system.

---

## Core product principles
- LLM must NOT make final hard scheduling decisions.
- Scheduling logic must remain deterministic and explainable.
- LLM SHOULD actively power natural-language input, intent understanding, preference modeling, explanation, and replanning.
- Real-world API integration should improve correctness, not reduce stability.
- Prefer durable product engineering over short-term hacks.
- Product quality is defined by correctness, contract stability, resilience, observability, and maintainability.
- Product evolution should move toward LLM-native interaction while preserving deterministic execution boundaries.

---

## Current implementation baseline
At the current stage, the repository includes or is expected to include:

- Frontend: Next.js App Router + TypeScript
- Backend: FastAPI
- External services: Amap geocoding and walking route APIs
- Scheduling engine: deterministic itinerary planner with fixed-time constraints and travel-time-aware ranking
- Travel metadata: backend-exposed fields that support explanation and timeline rendering
- Product direction in progress: natural-language itinerary input and LLM-assisted planning interaction

This baseline may evolve, but changes should remain incremental and controlled.

---

## LLM role definition

### LLM is responsible for
- parsing free-form user travel requests
- extracting structured planning intent
- identifying hard constraints and soft preferences
- helping expand or clean candidate POIs
- generating user-facing explanations
- supporting conversational replanning
- improving interaction quality and product intelligence
- recognizing time constraint state
- distinguishing fixed-duration planning from interest-driven duration estimation
- helping normalize partial or flexible time availability into structured planning state
- helping derive stay recommendation after an itinerary skeleton is clear

### LLM is NOT responsible for
- final hard scheduling decisions
- violating fixed constraints
- bypassing deterministic planner rules
- directly replacing route/time-based planning logic
- silently inventing execution-layer facts

### Design rule
Use the LLM as the intelligence and interaction layer above the planner.
Use the planner as the execution and verification layer beneath the LLM.

---

## Engineering rules
- Prefer the smallest safe change that moves the product forward.
- Do not refactor unrelated code.
- Do not rename fields unless explicitly instructed.
- Keep backend and frontend contracts aligned.
- Keep response schemas stable unless the task explicitly changes them.
- Reuse already-computed external API results when possible.
- Avoid duplicate geocoding or route calls.
- Add fallback behavior explicitly when external APIs may fail.
- Favor observability over silent behavior when debugging product logic.
- Changes that introduce LLM integration must preserve deterministic execution boundaries.
- Changes that improve natural-language interaction are in scope when they support the active product direction.

---

## Product behavior rules
- Hotel is optional in the main planning flow.
- If a hotel is explicitly provided, it acts as a known anchor and may fail the request if it cannot be resolved.
- If a hotel is not provided, interest-first itinerary planning should still work using other available anchors or itinerary-derived fallback context.
- Scenic spots and restaurants are non-critical and may be skipped if geocoding fails.
- Fixed items must preserve fixed scheduling behavior.
- Travel metadata shown in API responses should come from the same scheduling decision path when possible.
- Frontend display logic should reflect backend decision logic faithfully.
- LLM-generated interpretations must be transformed into explicit structured inputs before entering deterministic planning.
- When ambiguity exists in user input, prefer explicit structured clarification over implicit hidden assumptions.

---

## Product evolution priorities
When choosing what to build next, prefer work that supports one of these directions:

1. Natural-language itinerary input
2. Preference extraction and structured planning intent
3. Better explanation and conversational replanning
4. Safer and more explicit planner contracts
5. More resilient external API integration
6. Better observability for decision paths
7. Better frontend representation of actual backend reasoning
8. Better support for time-flexible trip planning and trip-scope estimation
9. Stay recommendation that follows itinerary skeleton planning rather than forcing hotel-first input

Do not let low-value polish displace core product-direction work.

---

## Scope control
- Do not redesign the scheduler unless explicitly requested.
- Do not introduce clustering, global optimization, or ML-based scheduling unless explicitly requested.
- Do not change frontend for backend-only tasks.
- Do not change backend for frontend-only tasks.
- Do not add “nice-to-have” features unless they directly support the requested product goal.
- Do not treat LLM integration as optional polish when it is part of the active product direction.
- Do not allow LLM-facing improvements to erode deterministic execution safety.
- Do not expand scope simply because a broader redesign seems attractive.

---

## Expected working style
Before editing:
- explain the smallest correct next step
- identify the exact files to change
- state assumptions clearly
- clarify whether the task belongs primarily to:
  - LLM interaction layer
  - deterministic execution layer
  - frontend display layer
  - contract / integration layer

After editing:
- summarize exactly what changed
- list files changed
- explain why the change is correct
- list regression risks
- provide exact local test steps
- note any remaining limitations honestly
- state whether the change advances:
  - product intelligence
  - execution correctness
  - resilience
  - contract safety
  - user-facing explainability

---

## Multi-agent workflow
For non-trivial tasks, act as a product engineering team with internal role separation:

### 1. Planner
Responsibilities:
- define the smallest correct next step
- constrain scope
- protect architecture discipline
- keep the work aligned with active product direction

### 2. Implementer
Responsibilities:
- make the minimal correct code change
- preserve current contracts and behavior unless explicitly changing them
- avoid unnecessary abstractions or refactors

### 3. Reviewer
Responsibilities:
- check field-name consistency
- check backend/frontend contract safety
- check regression risk
- check for unnecessary API-call duplication
- check whether the patch is suitable for continued product iteration

### 4. LLM product reviewer
Responsibilities:
- check whether the change supports LLM-native product direction
- ensure the LLM layer grows in the right places
- ensure deterministic scheduling boundaries remain intact
- prevent the product from drifting into “traditional app + superficial AI”
- verify that LLM integration improves interaction, not execution ambiguity

### 5. Hardening reviewer
Responsibilities:
- check resilience and fallback correctness
- check quota / rate-limit sensitivity
- check observability and debuggability
- check whether the patch increases system fragility
- check whether the patch is safe under real API conditions

---

## Return format
When completing a task, return:
- summary
- files changed
- why this change is correct
- risks
- exact local verification steps

For larger tasks, also return:
- assumptions
- contract impact
- whether this change primarily advances:
  - LLM interaction capability
  - deterministic planning capability
  - frontend explanation quality
  - resilience / hardening
  - product maintainability

---

## Final operating rule
This repository should evolve toward an LLM-native travel planning product.

The correct pattern is:

- LLM for understanding, organizing, explaining, and interacting
- deterministic systems for enforcing, computing, validating, and executing

Protect both layers.
Do not collapse one into the other.

## UI Design Skill

When working on frontend UI, visual design, layout, interaction prototypes, dashboards, trip timeline views, itinerary cards, or design-system changes, first read and follow:

`skills/web-design-engineer/SKILL.md`

Use this skill especially for:
- premium travel planning UI
- Trip Skeleton timeline design
- Completion Intelligence panel
- place detail cards
- route editing interactions
- visual critique and UI polish
- component-level frontend design

Important rules:
- Do not start coding UI changes before declaring the design system.
- Avoid generic AI-style UI patterns.
- Preserve existing backend contracts and frontend behavior.
- Prefer v0 visual direction first, then full implementation.
- Keep UI changes scoped and reviewable.
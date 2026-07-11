## 🧠 Project Title

**AI Travel Itinerary Planner (Full-Stack MVP)**

---

## 📌 Overview

This project is a full-stack AI-powered travel itinerary planning system.

It lets users start from interesting places, food, activities, fixed events, and time constraints first, then generates a structured multi-day travel plan based on deterministic scheduling logic and spatial heuristics.

Hotel is optional:
- if the user already knows it, it can be used as a planning anchor
- if not, the product can still build an itinerary skeleton first and suggest a stay area afterward

The system focuses on **planning efficiency, interpretability, and user-friendly output**, rather than generic recommendations.

---

## 🚀 Key Features

### 1. Intelligent Itinerary Generation

* Multi-day travel planning
* Morning / Afternoon / Evening time blocks
* Automatic day estimation if not provided
* Interest-first planning without requiring a hotel up front

### 2. Constraint-Aware Scheduling

* Supports fixed day and fixed time constraints
* Supports semi-fixed availability windows for boundary days and one explicit indexed day
* Prioritizes user-defined constraints before filling remaining slots

### 3. Distance-Aware Heuristic

* Greedy scheduling based on proximity
* Reduces unnecessary travel between locations

### 4. Human-Readable Output

* Timeline-style UI
* Structured by day and time blocks
* Includes explanation layer for each block
* Shows availability trimming, fixed-event placement, and boundary-anchor influence when meaningful

### 5. Stay Recommendation After Itinerary

* If a hotel is not provided, the product can suggest a stay area after itinerary generation
* Stay recommendation is derived from the itinerary skeleton, not from a huge hotel-search subsystem
* Recommendation explains why the area fits the current trip and whether it is best for Day 1, balanced across days, or convenient for departure

---

## 🏗 System Architecture

```text
User Input (Frontend)
        ↓
API Request (Next.js → FastAPI)
        ↓
POI / Optional Anchor Normalization
        ↓
Scheduling Engine (core logic)
        ↓
Itinerary JSON + Stay Recommendation
        ↓
Frontend Rendering (timeline UI)
```

---

## ⚙️ Tech Stack

### Frontend

* Next.js (App Router, TypeScript)
* React (hooks)
* Minimal CSS / inline styling

Create `frontend/.env.local` from `frontend/.env.example` when testing the mobile route editor map.

* `NEXT_PUBLIC_AMAP_WEB_KEY` enables the browser-side Amap route workspace.
* `NEXT_PUBLIC_AMAP_SECURITY_JS_CODE` sets Amap JSAPI `securityJsCode` before the browser script loads.
* `NEXT_PUBLIC_API_BASE_URL` points the frontend at the FastAPI backend and defaults to `http://localhost:8000`.
* Without `NEXT_PUBLIC_AMAP_WEB_KEY`, the route editor safely falls back to the list-first experience and remains editable.
* Without `NEXT_PUBLIC_AMAP_SECURITY_JS_CODE`, the previous no-security-code behavior is preserved for environments that do not require it.

### Backend

* FastAPI
* Pydantic (data validation)
* Modular architecture (api / core / schemas / services)

### Backend Environment

Create `backend/.env` from `backend/.env.example` for local configuration.

* `APP_ENV=development` keeps local development permissive.
* `POI_DISCOVERY_MODE=fallback` allows local/demo fallback to curated safety-net candidates.
* `CORS_ALLOW_ORIGINS=*` keeps local browser development permissive; production should set explicit origins such as `https://your-domain.com`.
* `APP_ENV=production` defaults `POI_DISCOVERY_MODE` to `required`.
* `AMAP_API_KEY` is required for production geocoding, walking routes, stay/departure advice, and realtime Completion Task candidate discovery.
* `AMAP_REQUEST_TIMEOUT_SECONDS` controls Amap geocoding/search/route request timeouts and defaults to `10`.
* `OPENAI_INTENT_MODEL`, `OPENAI_INTENT_TIMEOUT_SECONDS`, and `OPENAI_DISAMBIGUATION_TIMEOUT_SECONDS` control the LLM interaction layer without changing deterministic scheduling.
* `LOG_LEVEL` controls backend logging verbosity and defaults to `INFO`.
* Without `AMAP_API_KEY`, the backend still runs in development/fallback mode, but POI discovery degrades to the built-in curated safety-net catalog and session candidate history.
* In production required mode, missing `AMAP_API_KEY` fails startup instead of silently serving incomplete POI discovery.

You can check runtime capability at:

```text
GET /readiness
```

If production is missing `AMAP_API_KEY`, readiness reports a failed POI discovery state; startup also fails unless `POI_DISCOVERY_MODE=fallback` is explicitly set for demo deployments. Readiness also reports non-secret runtime configuration such as configured provider timeouts and whether API keys are present.

### Backend Observability

Every backend response includes:

* `X-Request-ID`, using the incoming request id when supplied or generating one server-side.
* `X-Process-Time-Ms`, reporting request handling time for lightweight local debugging.

The frontend sends `X-Request-ID` automatically on JSON API calls. `/apply-completion-task` also accepts `X-Idempotency-Key`, which the frontend uses to prevent duplicate inserts when a Completion Intelligence action is retried or double-clicked.

---

## ✅ Local Verification

Run these commands from the repository root before shipping product changes:

```bash
cd frontend
npm run typecheck
npm run build
```

```bash
backend/.venv/bin/python -m unittest discover -s backend/tests -t backend
```

If backend dependencies are freshly installed, `pytest` also works from the backend directory:

```bash
cd backend
python -m pytest
```

---

## 🧠 Core Logic (Scheduler)

The scheduling engine is built with:

* Time-block-based allocation (morning / afternoon / evening)
* Greedy heuristic for POI selection
* Constraint prioritization
* Simple rule-based preference:

  * Daytime → scenic spots
  * Evening → restaurants

---

## 🔍 Design Philosophy

* **LLM is used for interaction, parsing, and explanation**
* Final scheduling remains deterministic and explainable
* The main planning flow is itinerary-first, not hotel-first
* Focus on **interpretability over black-box AI**

---

## 📸 Demo

（你可以放截图）

---

## ⚠️ Limitations (Honest & Professional)

* Exact hotel search / booking is out of scope
* Stay recommendation is area-oriented, not a full accommodation marketplace
* No user authentication
* POI discovery is provider-backed when `AMAP_API_KEY` is configured; the curated catalog is only a safety net, not a full POI data platform

---

## 🔮 Future Improvements

* Improve stay-area recommendation quality
* Add richer POI discovery and cleanup
* Expand conversational planning and replanning
* Improve route quality without losing explainability

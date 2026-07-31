# AI Trip Compiler V1 Scope

## User and job

The V1 user already knows a destination and some places, reservations, or time
limits, but does not want to manually assemble a two or three day itinerary.

Job to be done: paste those fragments, confirm what matters, and receive a
saved, readable trip skeleton that can accept one safe local repair.

## Golden path

```text
text input
-> typed travel intent
-> user confirmation
-> deterministic persisted plan (Revision 1)
-> daily route view
-> server-selected relax-day preview
-> confirmed compensating route revision
```

## In scope

- One city, one to three days, text input, and up to eight user-supplied places.
- Must-visit and adjustable places, fixed events, pace, meal preferences, and
  arrival/departure limits.
- Server-authoritative planning, SQLite persistence, capability cookie access,
  revision creation, and one `relax_day` repair goal.
- Explicit information-insufficient and hard-conflict states.

## Non-scope

- Direct Xiaohongshu, video, account, or browser-bookmark integrations.
- OCR, maps as an editing surface, hotels, tickets, payments, collaboration,
  multi-city routing, and a general drag-and-drop route editor.
- Planner execution from an unconfirmed or fixture-backed browser state.

## Existing capabilities retained

The live surface reuses the existing FastAPI planner, route calculation fallback,
SQLite Trip/TripRevision persistence, mutation proposal/apply semantics, stale
proposal protection, and idempotent mutation apply.

`/product-reset-preview` remains a visual reference. `/trip-compiler` is the
only live V1 route and must not import prototype fixtures.

## Success measures

- A first-time user can reach a saved two-day route in one input and one
  confirmation action.
- Fixed events and hard arrival/departure conflicts are not silently changed.
- A repair preview does not create a revision; one confirmed apply creates one.
- Chromium runs the complete, insufficient-information, conflict, and repair
  scenarios against real Next.js, FastAPI, and temporary SQLite.

## Deferred work

- Durable compiler-intent revisions separate from the planner input snapshot.
- Exact calendar dates for relative language such as “this weekend”.
- Provider-verified travel mode and calculation status on every route leg.
- Broader repair choices and full TripRevision history in the consumer surface.

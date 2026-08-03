# Product Reset: Golden Path Prototype

## Current user problem

The application has accumulated credible planning, constraint, preview, and revision
capabilities, but the first screen asks a casual traveler to interpret the system
before it has helped them. The current entry combines a large conceptual promise,
an illustrative route surface, completion tasks, and intent analysis. That makes a
simple two-day trip feel like an engineering workflow.

## Golden-path user

A traveler who already knows a destination and a few places they want to visit,
and wants a clear, adjustable, saveable two- or three-day independent trip quickly.

They are not a professional planner, group coordinator, source-research user, or
booking operator in this first experience.

## Primary job to be done

"Turn my short description into a route I can understand at a glance, then help
me make one safe, small change when a day is too full."

## Current experience problems

1. The home screen presents implementation concepts and supporting surfaces before
   a traveler has supplied a request.
2. Intent confirmation and executable route output are separated by product
   vocabulary and dense summary cards rather than a single, obvious progression.
3. The existing route workspace is valuable for later inspection, but its map,
   readiness, completion, and revision controls compete with the first answer to
   "what am I doing today?"

## Keep, hide, remove, defer

| Decision | Product capability | Reason in the golden path |
| --- | --- | --- |
| Keep | Intent compiler, fixed-arrangement handling, deterministic planner preview, mutation preview/apply, stale and idempotency protection | These remain the trustworthy execution substrate when the prototype is connected to production APIs. |
| Hide by default | Revision identifiers, provenance graphs, planner traces, readiness internals, mutation digests, evidence diagnostics | They are useful inspection tools, not input required to start a simple trip. |
| Remove from the first screen | Decorative route mockup, completion queue, duplicate workspace entry points, technical status summaries | They delay the first useful action and obscure the request-to-route flow. |
| Defer | Maps, hotel and flight flows, import research, collaboration, agent behavior, advanced risk rules, full route editor | They may return as deliberate secondary surfaces after the core route is understood. |

## New information architecture

The first-run experience has three states inside one isolated route:

1. **Say what you want**: one natural-language field and up to three examples.
2. **Confirm the important bits**: destination, days, pace, places, and fixed
   arrangements in plain language; source details remain collapsed.
3. **See the route and repair one day**: daily timeline, travel legs, protected
   arrangements, load explanation, and one local before/after repair.

The production home page is intentionally unchanged in this round. The prototype
is a fixture-only decision aid for testing the information architecture before any
existing API surface is rewired.

## Prototype criteria

- A traveler sees one primary action on the first screen.
- A normal Hangzhou two-day route is visible after two primary clicks or fewer.
- Day 1 is visible without navigating away from the route state.
- Shanghai demonstrates that a fixed appointment is visibly protected.
- A rushed day shows an understandable before/after repair that moves only a
  system suggestion to available capacity on day 2.
- No default screen exposes revision IDs, digests, trace IDs, API names, or
  provenance internals.
- The same interaction stays usable at 1440x900 and 390x844 without horizontal
  scrolling.

## Explicit non-goals

- No backend endpoint, schema, database, planner, mutation, or `TripRevision`
  behavior changes.
- No persistence: applying the prototype repair changes local fixture state only.
- No production home-page replacement or migration of existing workspace code.
- No map, provider lookup, booking, hotel, flight, import, agent, or collaboration
  feature work.

## Future backend integration seams

The fixture models deliberately mirror the user-facing parts of later contracts:

- `TripDraft` can be hydrated from the existing Draft Trip and intent compiler.
- `TripIntentSummary` can be built from the confirmed intent envelope without
  exposing its technical representation.
- `TripDay`, `Activity`, `TravelLeg`, `FixedEvent`, `DayLoad`, and `RouteRisk`
  can be adapted from the frozen deterministic preview.
- `RepairProposal` provides the single boundary to later mutation preview/apply.
  The production adapter must preserve base-revision, idempotency, stale-state,
  confirmation, and compensating-revision guarantees already present in the
  backend.

Until that adapter exists, `dataSource: "prototype_fixture"` is rendered and
tested as an explicit local-only state rather than being mistaken for a saved trip.

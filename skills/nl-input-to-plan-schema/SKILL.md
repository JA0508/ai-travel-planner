---
name: nl-input-to-plan-schema
description: Design, implement, or review the natural-language-to-structured-itinerary-input layer for this LLM-native travel planning product.
---

# NL Input to Plan Schema

## Purpose
This skill must support both:
- time-boxed planning, where duration is fixed or mostly fixed
- interest-driven planning, where duration is flexible and trip scope may need to be estimated first

Time flexibility is a first-class input dimension.
It must not be treated only as a missing `trip_days` field.

Use this skill when the task involves adding, refining, or validating the natural-language input layer of the travel itinerary planning system.

This skill exists to move the product toward an LLM-native interaction model while preserving the deterministic execution boundary of the planner.

The goal is not to let the LLM schedule the trip directly.

The goal is to let the LLM transform free-form user intent into explicit, structured planning input that the deterministic planner can safely consume.

## Product boundary
This skill belongs to the LLM interaction layer.

The parsing layer should detect whether the user is asking for:
- fixed-duration planning
- semi-fixed-duration planning
- flexible-duration planning

If duration is flexible, the system may first estimate a reasonable trip scope before deterministic itinerary planning.

LLM may:
- parse user travel intent
- extract hard constraints
- extract soft preferences
- identify candidate POIs
- organize ambiguous user input
- prepare structured itinerary intent
- support explanation and later replanning

LLM must NOT:
- make final hard scheduling decisions
- violate fixed constraints
- replace deterministic route/time-based planning
- invent execution-layer facts and pass them off as certain

## Use this skill when
Use this skill when:
- adding a natural-language itinerary input box
- designing the structured schema that comes out of LLM parsing
- building a backend endpoint such as `POST /parse-itinerary-intent`
- mapping user travel text into planner-ready fields
- extracting city, trip length, hotel when known, POIs, fixed events, and preferences
- reviewing whether a parsing schema is compatible with the current planner
- improving ambiguity handling in user input
- adding a confirmation step between parsing and scheduling

## Do NOT use this skill when
Do NOT use this skill when:
- the task is only about scheduler internals
- the task is only about frontend visual polish
- the task is only about external API hardening
- the task is only about route ranking or geocoding implementation
- the task is asking for final schedule generation directly from the LLM

## Design rule
The LLM may interpret user intent.

The deterministic planner must execute the final planning logic.

Always preserve this boundary.

Natural-language parsing output must become:
- explicit
- structured
- reviewable
- planner-compatible
- safe under ambiguity

## Expected structured output categories
Prefer an output schema that can support at least:
- city
- trip_days
- hotel (optional when already known)
- scenic_spots
- restaurants
- fixed_events
- preferences
- availability_windows
- arrival_anchor / departure_anchor when useful
- ambiguity or clarification notes when needed

Example shape:

```json
{
  "city": "Shanghai",
  "trip_days": 1,
  "hotel": {
    "name": "南京路步行街附近酒店"
  },
  "scenic_spots": [
    { "name": "外滩" },
    { "name": "豫园" }
  ],
  "restaurants": [
    { "name": "云南南路美食街" }
  ],
  "fixed_events": [
    {
      "name": "上海博物馆",
      "day": 1,
      "start_time": "14:00:00",
      "end_time": "16:00:00"
    }
  ],
  "preferences": {
    "pace": "relaxed",
    "themes": ["old_shanghai", "local_food"],
    "avoid": []
  }
}
```

## Time-state requirement
The parsing result should explicitly represent time constraint state.

At minimum, the system should be able to distinguish:
- fixed_duration
- semi_fixed_duration
- flexible_duration

This state may later be normalized into a dedicated planning input state rather than being represented only by `trip_days`.

Example for flexible-duration parsing:

```json
{
  "city": "Shanghai",
  "trip_days": null,
  "hotel": null,
  "scenic_spots": ["外滩", "豫园", "武康路"],
  "restaurants": ["本帮菜"],
  "fixed_events": [],
  "preferences": {
    "pace": "relaxed",
    "themes": ["city_walk", "local_food"],
    "avoid": []
  },
  "time_state": "flexible_duration"
}
```

## Planning-state normalization
The parsing result does not need to be identical to final planner input.

This system may use an intermediate planning input state layer to normalize:
- time state
- hotel state
- POI state
- fixed-event state
- preference state

Preferred flow:

free text -> parsed intent -> planning input state -> deterministic planner

This helps the system support vague inputs, partial inputs, and flexible-duration cases without forcing premature scheduler redesign.

## Product-direction note
Do not assume hotel must be known before meaningful planning can begin.

In this product, users often start from:
- places they want to visit
- food they want to try
- activities they care about
- time constraints they already know

Hotel may be:
- already known and usable as an anchor
- roughly known
- unknown until after the itinerary skeleton is clearer

Schema and parsing decisions should preserve this interest-first flow.

## Review checklist
- Does the parsing layer explicitly recognize time flexibility?
- Does it distinguish time-boxed planning from interest-driven planning?
- If trip duration is not fixed, does the design allow trip-scope estimation before deterministic scheduling?
- Does the parsing output separate hard constraints from soft preferences?
- Does the design allow a planning input state layer between parsed intent and scheduler input?
- Does the patch preserve deterministic scheduling boundaries?
- Does the patch avoid letting the LLM make final schedule decisions?
- Does the schema remain explicit, reviewable, and safe under ambiguity?

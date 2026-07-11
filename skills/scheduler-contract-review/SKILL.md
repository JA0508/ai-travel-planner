---
name: scheduler-contract-review
description: Review scheduler-related changes for deterministic behavior, schema safety, field-name consistency, and backend/frontend contract stability.
---

# Scheduler Contract Review

## Purpose
Use this skill when a change may affect:
- scheduler logic
- itinerary response schema
- scheduling-related backend models
- frontend itinerary rendering
- fixed-vs-flexible behavior
- travel metadata

This skill exists to stop subtle breakage in the most fragile part of the product:
the contract between the deterministic planner, the API response, and the frontend display.

## Use this skill when
Use this skill when:
- changing scheduler code
- changing ScheduledPOI or related response fields
- changing NormalizedPOI / HotelStay / planner-facing schema
- changing frontend timeline display of itinerary items
- adding or modifying travel metadata
- integrating LLM parsing output into planner-facing structures

## Do NOT use this skill when
Do NOT use this skill when:
- the task is purely UI polish with no data/contract effect
- the task is unrelated to itinerary generation
- the task is only about general documentation

## Review goals
Check whether the patch preserves:
- deterministic scheduling behavior
- fixed constraint behavior
- stable field names
- backend/frontend schema alignment
- response correctness
- explicit fallback behavior
- safe map API usage

## Pay special attention to
- current_anchor field names
- poi latitude / longitude fields
- type vs type.value usage
- duration field consistency
- optional vs required travel metadata
- optional vs required hotel / anchor behavior
- fixed vs non-fixed output behavior
- whether travel metadata comes from the actual decision path
- whether route lookups are duplicated unnecessarily
- whether LLM output is transformed into explicit structured inputs before planner use
- whether stay recommendation or hotel-related response fields match the current interest-first product direction

## Required output
Return:
- what changed
- contract risks
- mismatch points if any
- deterministic behavior assessment
- whether the patch is safe to merge
- exact local verification checklist

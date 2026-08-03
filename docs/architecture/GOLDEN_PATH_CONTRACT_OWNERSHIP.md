# Golden Path Contract Ownership

`/product-reset-live` is a production vertical slice. It is deliberately
separate from `/product-reset-preview`, which remains fixture-only.

| Concern | Authoritative owner | Client responsibility |
| --- | --- | --- |
| Natural-language interpretation | Intent Compiler and its untrusted proposal adapter | Submit the original text and show the returned outcome |
| Destination, dates, pace, travel boundaries | Immutable Draft Intent revision | Confirm rather than infer hidden values |
| Place identity and source links | Verified TripCandidate / intent provenance | Render the returned ownership label |
| Fixed appointment | Deterministic handoff and scheduler | Render as protected; never offer a move |
| Daily load, available capacity and risk | `PlannerRealismSummary` | Render the server classification and explanation |
| Route legs and their certainty | Frozen itinerary snapshot | Render actual returned duration/status; do not invent a reason |
| Repair candidate and destination day | `golden_path_repair` | Submit only target day and `relax_day` |
| Proposal digest, stale validation, idempotency | SQLite proposal/revision transaction | Keep and submit the server proposal digest |
| Saved version and lineage | `TripRevision` / `RevisionOperation` | Refresh from the apply response |

## Read model

The live route renders the server snapshot as activities, route legs, fixed
events, daily loads and risks. A scheduled activity is labelled only from
canonical metadata:

- `user_fixed`: `is_fixed` or `source_type=user_fixed`
- `system_suggested`: an automatic scheduled source type
- `user_optional`: candidate provenance field path `poi.optional_candidates`
- `user_must`: remaining confirmed user candidate provenance

This mapping does not use names, array positions or client-generated state.
When `placement_reason` is absent, the UI says that the reason is unavailable;
it does not synthesize a planner explanation.

## Prohibited client authority

The client cannot select an activity, select a target day, construct a mutation
command, apply a snapshot, calculate a route metric, or create a revision. It
may only request a repair for a rushed day and review the returned proposal.

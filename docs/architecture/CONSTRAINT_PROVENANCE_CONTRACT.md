# Constraint Provenance Contract

## Purpose

The Trip Compiler converts a confirmed `TravelIntent` into a deterministic
`ConstraintGraph` before it asks the scheduler for route candidates. The graph
is a derived, reviewable planning artifact. It is not a second trip persistence
model and it never creates a Trip or TripRevision by itself.

## Node contract

Every node has a stable id, `kind`, `strength`, `status`, human-readable value,
and at least one source reference. Supported kinds are `destination`,
`trip_duration`, `arrival_boundary`, `departure_boundary`, `fixed_event`,
`must_visit`, `optional_visit`, `pace`, `travel_mode`, `avoidance`,
`meal_preference`, and `daily_load`.

`strength` is either `hard` or `soft`. `status` is one of `satisfied`,
`unsatisfied`, `conflicting`, or `assumed`. A graph may contain assumptions, but
an unresolved hard node cannot be represented as planner-ready.

Each source reference points to a `SourceFragment` supplied by the confirmed
intent. A fragment records `stable_id`, source type, text, and optional raw-text
offsets. The compiler uses offsets only when it can locate the text exactly;
otherwise it stores a stable sentence fragment. Candidate generation rejects
unknown source references.

## Edges and conflicts

Edges describe relationships such as `bounds`, `requires`, `prefers`,
`conflicts_with`, and `derived_from`. A `ConflictCore` contains a stable code,
the smallest relevant node ids, source references, and a user-safe explanation.

At minimum the compiler identifies `arrival_after_fixed_event`,
`fixed_event_overlap`, `departure_before_required_activity`, and
`insufficient_travel_gap` when the available deterministic evidence proves the
conflict. Hard conflict cores stop candidate generation and the API returns a
recoverable `422`; no Trip or TripRevision may be created on that path.

## Authority boundary

Natural-language parsing proposes the `TravelIntent`. Graph compilation,
conflict detection, candidate feasibility, candidate selection, and persistence
are deterministic server work. A browser may edit a confirmed intent but cannot
send an itinerary skeleton to be saved. A direct confirmation edit creates a
`user_confirmation` source fragment and preserves the earlier source fragment.

## Digest boundary

`intent_digest` is a canonical digest of confirmed semantic intent. Candidate
ids, hashes, sorting, and selection verification derive from canonical JSON;
they do not depend on timestamps, random ids, or browser order.

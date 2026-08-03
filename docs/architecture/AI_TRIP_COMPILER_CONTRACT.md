# AI Trip Compiler V1 Contract

`/trip-compiler` treats language output as untrusted. The compiler validates a
typed intent, maps it into the established `ItineraryRequest`, and uses the
existing deterministic planner plus TripRevision persistence.

| Field | Canonical source | Owner | Type | Nullable | UI rule |
| --- | --- | --- | --- | --- | --- |
| destination | compiler response | compiler + user confirmation | `string` | yes | block planning when missing |
| trip days | compiler response | compiler + user confirmation | `1 \| 2 \| 3` | yes | V1 blocks planning outside one to three days |
| date window | compiler response | compiler + user confirmation | typed time-window object | fields yes | relative dates are not presented as confirmed calendar dates |
| pace | compiler response | compiler + user confirmation | relaxed/balanced/intensive | no | editable before planning |
| must visit | compiler response | user | typed place list | no list | show `必去` |
| optional place | compiler response | user | typed place list | no list | show `可调整` |
| fixed event | compiler response | user constraint | typed event list | fields yes | require day and complete range before plan |
| preference | compiler response | user | typed preference list | no list | editable token |
| constraint | compiler response | deterministic planner | typed constraint list | no list | describe hard time boundary |
| avoid item | compiler response | user | typed constraint list | no list | do not schedule as input seed |
| unresolved item | compiler response | compiler | typed queue | no list | blocking items disable planning |
| source fragment | submitted text | compiler | stable text fragment | no list | progressive disclosure only |
| activity time / duration | scheduled revision snapshot | deterministic scheduler | time + minutes | no | route timeline |
| travel leg | scheduled revision snapshot | route service / fallback | origin, destination, duration, distance | metrics yes | show unknown/estimated truthfully |
| travel mode | planner request | deterministic planner | enum | yes | MISSING CONTRACT for per-leg mode in V1 response |
| day load | planner realism response | deterministic analyzer | classification + metrics | no | never recompute in browser |
| risk | planner realism response | deterministic analyzer | typed issue list | no list | attach near the relevant day when possible |
| placement reason | scheduled revision snapshot | deterministic planner | `string` | yes | no client fallback |
| repair proposal | mutation proposal persistence | server mutation service | typed proposal + impact | no | browser submits goal only |
| revision | TripRevision persistence | SQLite service | immutable revision metadata + snapshot | no after plan | hidden in consumer UI |

## Ownership boundary

The browser may edit a typed intent and submit a repair goal. It may not select
an activity, write a mutation command, calculate a schedule, calculate a daily
load, or invent a travel leg/explanation. The local repair endpoint selects one
non-fixed, system-owned activity only after checking the target day for a safe
non-overlapping slot.

## Explicit gaps

- **MISSING CONTRACT:** durable standalone `TripIntentEnvelope` revision for a
  compiler submission; the current source of truth after confirmation is the
  persisted planner input and TripRevision snapshot.
- **MISSING CONTRACT:** absolute date resolution for relative phrases.
- **MISSING CONTRACT:** per-leg provider calculation status and canonical mode
  in the live V1 route response.

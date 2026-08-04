# Round 25.2 Completion Audit

| Capability | Current code and storage | Current test | Reliable | Round 25.2 action |
| --- | --- | --- | ---: | --- |
| Planning Run persistence | `planning_runs` and `SQLitePlanningRunRepository` | candidate API tests | Yes | preserve |
| Candidate snapshots | `planning_run_candidates` stores itinerary, metrics and comparison | deterministic generation tests | Yes | bind them to a frozen manifest |
| Event ledger | append-only event table and triggers | selection tests | Yes | add replay event proof |
| Capability access | HttpOnly hash-backed cookie | API selection tests | Yes | add restart and isolation coverage |
| Atomic selection | `select_candidate_atomically` and transaction-aware Trip write | rollback and different-candidate concurrency | Yes | add same-candidate races and remaining failure points |
| Revision lineage | selection operation metadata | lineage API test | Partial | include manifest digests |
| Snapshot manifest | immutable POI, route, strategy, and manifest JSON persisted by migration `0017` | manifest and lineage tests | Yes | preserve frozen inputs and digests |
| Frozen Decision Record Verification | `planning_run_replay.py` verifies stored candidates against the immutable manifest | verified, mismatch, unsupported-policy tests | Yes | scheduler re-execution from snapshots remains a future policy |
| Restart recovery | persisted SQLite record and cookie-scoped Planning Run access | two independent FastAPI processes share one database and select after restart | Yes | preserve as a process-level regression test |
| Browser acceptance | production Next.js build, real FastAPI and Chromium | five compiler flows including desktop refresh/record and mobile persisted candidate selection | Partial | add the remaining selected/expired/recovery-state assertions and screenshot review |

This audit records the implemented state through the current Round 25.2 slice.
A green candidate generation test alone is not evidence of replay or
process-restart recovery. The process-level restart gate now exists; browser
coverage remains deliberately partial until every persisted-state presentation
and reviewed screenshot is covered.

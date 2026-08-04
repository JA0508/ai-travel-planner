# Round 25.3 Diff Audit

| File group | Purpose | Direct user value | Reliability value | Required | Action |
| --- | --- | ---: | ---: | ---: | --- |
| `backend/app/services/planning_run_repository.py` and migrations | Persisted Planning Run, atomic selection, recovery authorization | Yes | Yes | Yes | Keep |
| `backend/app/services/planning_run_replay.py` and CLI | Frozen Decision Record Verification | No | Yes | Yes | Keep |
| `backend/app/services/constraint_planning.py` and schemas | Candidate snapshots, stable identity, manifest digests | Indirect | Yes | Yes | Keep |
| `backend/app/api/routes/trip_compiler.py` | Candidate creation, recovery, selection response | Yes | Yes | Yes | Keep |
| `backend/app/trips/service.py` | Preserve planning lineage through a controlled edit | Indirect | Yes | Yes | Keep |
| `backend/tests/test_plan_candidates.py` and restart test | Atomicity, recovery, verification, process restart evidence | No | Yes | Yes | Keep |
| Trip Compiler frontend files and E2E | Persisted route restoration and human-readable states | Yes | Indirect | Yes | Keep |
| `docs/architecture/*` and `docs/product/*` | Boundaries, acceptance evidence, operating record | Indirect | Yes | Yes | Simplify wording where it implied scheduler re-execution |

No duplicate Planning Run repository, scheduler, or Trip/Revision creation path was
introduced. The retained complexity is constrained to persistence boundaries and
the user-visible recovery path; full scheduler re-execution remains non-scope.

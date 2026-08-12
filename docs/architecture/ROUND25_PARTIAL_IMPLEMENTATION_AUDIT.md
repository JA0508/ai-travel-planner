# Round 25 Partial Implementation Audit

| Area | Current implementation | Correct | Incomplete | Required action |
| --- | --- | ---: | ---: | --- |
| Planning Run table | SQLite schema with immutable snapshot trigger | Yes | selection fields lack transaction owner | add transaction-aware selection API |
| Candidate table | snapshot, metrics, strategy input and rank persisted | Yes | no frozen POI/route manifest | persist manifest and replay it |
| Event Ledger | append-only events created and read | Yes | selection failure/replay events incomplete | append inside selection/replay transaction |
| Capability | HttpOnly run cookie and hashed lookup | Yes | secure flag not shared with Trip config | reuse runtime secure configuration |
| Refresh restore | URL restores persisted run without regeneration | Yes | selected/expired surfaces incomplete | model explicit restore states |
| Restart restore | SQLite records survive process reset | Yes | no dedicated restart proof | add integration and browser restart tests |
| Selection transaction | candidate validation, reservation, Trip, Revision 1, run update and events share one `BEGIN IMMEDIATE` transaction | Yes | no durable recovery operation is needed while all records share SQLite | retain API and failure-injection regression coverage |
| Idempotency | same key and payload return the existing Trip without a new revision; a different payload is rejected | Yes | replay rotates an opaque capability to reissue it safely | retain API coverage for both payload cases |
| Concurrent selection | two independent HTTP clients compete through SQLite CAS | Yes | only the different-candidate race is currently covered | add same-candidate/same-key race before closure |
| Failure recovery | test-only hook rolls back after reservation and after Revision creation | Partial | remaining injection points and lost-response simulation are absent | cover all declared failure points before closure |
| Frozen decision verification | intent, graph and strategy inputs stored | Partial | no verification service or policy handling | add verification service and CLI |
| Replay CLI | absent | No | absent | add `app.tools.verify_planning_run` |
| Provenance | first-fragment fallback removed | Partial | some generic fields may have no evidence | block hard constraints without evidence |
| Candidate strategies | relaxed removes optional; low-travel keeps ordered inputs | Partial | route benefit is not yet guaranteed by data | use complete route metrics before label |
| Candidate metrics | availability windows use arrival/departure | Partial | meal and route inputs remain simplified | freeze route snapshots and expose unknowns |
| Route comparison UI | all day items render | Partial | visual hierarchy and state handling sparse | complete selector, record, expiry and mobile states |
| Mobile UI | existing responsive single column remains | Partial | no mobile acceptance | add real Chromium mobile coverage |

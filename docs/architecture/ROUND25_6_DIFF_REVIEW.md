# Round 25.6 Diff Review

| Change group | User value | Reliability value | Complexity | Decision |
| --- | --- | --- | --- | --- |
| Planning persistence | Refreshing the candidate comparison does not discard a user's work. | Durable, capability-bound candidate snapshots survive process restart. | Medium | Keep |
| Atomic selection | Saving a candidate produces one clear saved trip. | Planning Run, Trip, Revision 1, and ledger events commit together. | Medium | Keep |
| Concurrency fix | A duplicate click or parallel request cannot create duplicate trips. | Selection reservation and idempotency payload binding keep the first decision stable. | Medium | Keep |
| Response-loss recovery | Retrying after a lost response reopens the same saved trip. | The original Planning Run capability can safely reissue a Trip capability without a second revision. | Medium | Keep |
| Frozen record verification | Engineering can detect a corrupted persisted decision record. | Verifies immutable candidate IDs, order, hashes, itineraries, metrics, and set hash without provider calls. | Low | Simplify |
| Recovery UI | Users can distinguish restored, expired, and saved route states. | Avoids accidental replanning or duplicate selection after recovery. | Low | Keep |

## Simplifications applied

- Removed the unused public replay endpoint. Frozen Decision Record Verification remains a backend-only verification tool and test contract; it does not claim to re-run the scheduler.
- Removed unused repository selection helpers left behind by the atomic selection implementation.
- No capability values, cookies, or raw user text are written to Planning Run events or logs.

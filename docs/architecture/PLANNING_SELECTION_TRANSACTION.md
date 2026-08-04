# Planning Candidate Selection Transaction

Selecting a candidate is a single SQLite transaction. It verifies the Planning
Run capability, expiry, candidate hash, intent digest, and idempotency payload;
creates the Trip and immutable Revision 1; marks the run selected; and appends
the ledger events. One run can select one candidate only.

An identical idempotency key returns the original Trip. A different candidate
after selection is rejected as recoverable and identifies the already selected
candidate and Trip without exposing a capability. A transaction failure rolls
back the Trip, Revision, run status, and events together.

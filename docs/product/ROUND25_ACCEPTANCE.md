# Round 25 Acceptance

Round 25 accepts a Planning Run only when candidates survive a process restart,
their frozen decision records can be verified without parser or provider calls, and
exactly one candidate selection atomically creates Trip Revision 1.

Candidate labels must be supported by measured coverage, available time, and
route completeness. Missing route data remains unknown rather than zero. The
comparison UI must expose the full route, recovery state, and a user-readable
planning record on desktop and mobile.

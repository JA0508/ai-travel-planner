# Frozen Decision Record Verification Contract

Frozen Decision Record Verification reads only the persisted Planning Run snapshot. It never invokes
the intent parser, an LLM, a POI provider, or a route provider.

The replay service requires the original planner policy and snapshot contract
versions. The current policy performs **frozen-decision verification**: it
checks the persisted candidate records against the immutable manifest, including
candidate IDs, order, hashes, itineraries, metrics, and the candidate-set hash.
It does not yet regenerate candidate itineraries from frozen scheduler inputs.

The result is `verified`, `mismatch`, `unsupported_policy_version`, or
`invalid_snapshot`; an unavailable policy is never silently replaced by the
latest policy. A future policy may add scheduler re-execution only when it can
consume the frozen POI and route snapshots without provider access.

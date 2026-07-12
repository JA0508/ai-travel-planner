# Architecture Decision Records

This directory stores **Architecture Decision Records (ADRs)**.

An ADR is a short document that records a durable product or engineering decision:

- what problem required a decision
- what option was selected
- why it was selected
- what trade-offs or consequences follow

ADRs are useful when a future contributor asks:

> “Why does the system work this way?”

They are not task plans, meeting notes, or general documentation.

## File naming

Use a sequential number and a concise title:

```text
0001-source-to-executable-trip-workspace.md
0002-llm-deterministic-boundary.md
0003-trip-revision-as-change-unit.md
```

## Status values

Use one of:

- Proposed
- Accepted
- Superseded
- Deprecated

## Template

```md
# ADR-NNNN: Decision title

## Status

Proposed

## Date

YYYY-MM-DD

## Context

What problem or architectural pressure requires a decision?

## Decision

What was selected?

## Consequences

### Positive

- ...

### Negative / trade-offs

- ...

## Alternatives considered

- ...

## Related documents

- ...
```

## Usage rule

Create an ADR only for decisions expected to remain important across multiple
features or releases.

Routine implementation details should remain in code, tests, issues, or pull requests.

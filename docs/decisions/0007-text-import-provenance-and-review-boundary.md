# ADR-0007: Text Import Provenance and Review Boundary

## Status

In review

## Date

2026-07-15

## Context

The product direction is Source-to-Executable Trip Workspace. Before URL,
image, PDF, OCR, or full Intent Compiler work can safely enter the repository,
the system needs a durable source boundary: raw user material must be preserved
as evidence, extracted facts must remain traceable to exact source spans, and
human review must happen before anything can influence executable trip state.

The repository already has `TripCandidate` and typed candidate admission. That
means import should not invent another candidate model or jump directly to
`TripRevision`.

## Decision

The first import slice supports pasted text only:

```text
pasted text
→ SourceArtifact
→ ImportJob
→ ExtractedMention
→ ResolvedPlaceCandidate
→ ImportReviewDecision
→ TripCandidate
```

Raw source and candidate state are deliberately separated. A `SourceArtifact`
stores private text bytes behind an opaque storage key and checksum. JSON
metadata never returns the storage path or full raw text. Review display fetches
the text through a capability-protected artifact endpoint with private/no-store
headers.

Each `ExtractedMention` stores code-point offsets, raw text, bounded context,
classification, confidence, warning codes, and a content digest. The service
validates that `source_text[start:end] == raw_text` before persisting the
mention.

LLM extraction is not used as canonical identity authority. The current
production path uses a deterministic, limited extractor and deterministic local
place resolver. Future LLM adapters may propose schema-valid mentions, but
provider identity and user confirmation remain separate.

Provider or resolver output creates `ResolvedPlaceCandidate` records, not final
places. Ambiguous, missing, partial, provider-failed, and cross-city states stay
explicit until the user reviews them.

Review decisions are append-only and use optimistic `review_version` plus
idempotency keys. Stale review updates return `stale_import_review` instead of
last-write-wins.

Import commit only creates or reuses `TripCandidate` records for confirmed place
mentions. Non-place mentions are preserved as reviewed import context. Commit
does not create `TripRevision`, mutate TripIntent, run the planner, admit
candidates, or write arbitrary itinerary snapshots.

## Consequences

### Positive

- imported places are traceable back to artifact and exact source span
- duplicate text artifacts are detected by checksum
- prompt-injection-like text is treated as source data, not instructions
- user confirmation is distinct from extractor or resolver confidence
- confirmed places enter the existing TripCandidate boundary
- import commit is retry-safe and does not change executable itinerary state
- URL/image/PDF adapters can reuse the same artifact, mention, resolution, and
  review model later

### Negative / trade-offs

- deterministic extraction coverage is intentionally limited
- complex free-form travel prose may become partial review rather than a rich
  semantic import
- imported non-place constraints are not compiled into TripIntent yet
- local artifact storage is sufficient for development but not a cloud object
  storage solution
- existing immutable TripCandidate records cannot be amended with new evidence
  after cross-job dedupe; import commit records preserve the later evidence

## Alternatives considered

- **Direct LLM-to-itinerary import:** rejected because it would collapse source
  extraction, identity resolution, scheduling, and execution into an unsafe
  generative write.
- **ImportedCandidate model:** rejected because it would duplicate
  `TripCandidate` and weaken the existing admission boundary.
- **Automatic TripRevision on import commit:** rejected because source review is
  not an executable itinerary mutation.
- **URL/image/PDF first:** rejected because those adapters need the same
  provenance and review contract; text is the smallest auditable slice.

## Related documents

- ADR-0001: Source-to-Executable Trip Workspace
- ADR-0003: TripRevision Persistence and Concurrency
- ADR-0006: Trip Candidate Admission and Mutation Closure

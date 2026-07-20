# ADR-0010: Layout-Aware Document Text Extraction

## Status

In review

## Date

2026-07-20

## Context

Import-to-Executable needs images and PDFs to become reviewable source text, but
document extraction is a larger trust boundary than text import. The system must
not turn an accepted binary artifact directly into itinerary state, silently run
OCR, or lose the page/region provenance needed to review extraction errors.

## Decision

Document extraction starts only from an image/PDF artifact that passed the
quarantine-first inspection gate:

```text
accepted binary artifact
→ extraction strategy decision
→ native PDF text or bounded page rendering
→ local OCR when explicitly needed and available
→ layout blocks / lines / tokens
→ deterministic reading order
→ derived_document_text SourceArtifact
→ document_layout_manifest SourceArtifact
→ document_text_span_map SourceArtifact
→ existing mention extraction and place resolution
→ Import Review Inbox
→ explicit review commit to TripCandidate
```

PDF extraction is native-text-first. Pages with native text do not run OCR.
Pages without native text may use bounded page rendering plus local OCR only
when selective PDF OCR is enabled. Image extraction uses local Tesseract OCR
after inspection and sanitized derivative creation. OCR capability metadata
reports the engine, requested languages, installed languages, missing languages,
and confirms that no silent fallback was used.

The layout model uses stable page, block, line, and token IDs, normalized
top-left bounding boxes, and `layout-reading-order-v1`. The derived text spans
store offsets, page numbers, layout IDs, reading order, source method, confidence
where available, and privacy-safe warning codes. Mention evidence is resolved by
overlapping extracted mention offsets with stored document spans.

The browser may show document extraction evidence and normalized bbox overlays,
but it does not inline-render original PDFs or original uploaded images. Original
binary bytes remain private artifacts. Review commit still creates or reuses
`TripCandidate` records only; it does not create a `TripRevision`, mutate the
itinerary, run the planner, or bypass Import Review.

## Consequences

### Positive

- Native text PDFs avoid unnecessary OCR cost and OCR error.
- Selective PDF OCR is explicit and page-bounded rather than global fallback.
- Derived text, layout manifest, and span map have immutable artifact lineage.
- Reviewers can trace mentions back to page/region evidence.
- Existing Import Review and TripCandidate admission boundaries are reused.
- CI can prove production OCR availability separately from fixture tests.

### Negative / trade-offs

- Local Tesseract and language packs become required for production OCR smoke
  tests.
- PDF rendering remains deliberately bounded and is not a general PDF viewer.
- Native PDF coordinates are approximate when PDFs expose limited text geometry.
- The current UI shows compact evidence overlays, not a full document review
  canvas.
- Failed OCR produces explicit partial/failure semantics rather than silently
  falling back to weaker text.

## Related documents

- ADR-0007: Text Import Provenance and Review Boundary
- ADR-0008: Secure URL Import and Fetch Provenance
- ADR-0009: Quarantine-First Binary Artifact Inspection
- Product phase: F-002d Layout-Aware OCR and Document Text Extraction

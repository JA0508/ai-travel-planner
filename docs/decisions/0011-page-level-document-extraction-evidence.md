# ADR-0011: Persist page-level document extraction evidence

## Status

Accepted

## Date

2026-07-20

## Context

F-002d introduced inspection-gated image and PDF document extraction with layout
spans and mention evidence. The first implementation still treated PDF native
text extraction as page-global success once any text unit existed, rendered
mention bounding boxes over a synthetic browser surface, and did not persist
page-level extraction outcomes.

The product needs document extraction evidence that can be reviewed, retried,
and evaluated at page granularity without mutating a trip directly.

## Decision

Document extraction generations now include immutable page records. Each page
records extraction method, status, native-text quality, text/span counts,
retryability, warning/error codes, preview artifact references, and bounded
metadata for page dimensions.

PDF extraction uses a native-text quality threshold before accepting a page as
native text. Low-quality or empty pages may use selective rendered-page OCR when
enabled. Rendered PDF pages are bounded by pixel and byte limits and are stored
as private derived page-preview artifacts.

The Import Review UI loads page previews through a private endpoint and overlays
normalized mention bounding boxes on the real preview image.

Retry is page-addressed but revision-safe for extraction lineage: a retryable
page creates a new document extraction generation rather than modifying existing
page records in place.

## Consequences

- Reviewers can distinguish extracted, partial, failed, and retryable pages.
- Mention geometry is anchored to real sanitized image or rendered PDF previews.
- PDF native text is no longer accepted solely because one text unit exists.
- Existing Import Review commit semantics remain unchanged: extraction does not
  directly mutate the trip itinerary.
- Duplicate derived artifacts may be reused by checksum while extraction
  generations remain append-only.

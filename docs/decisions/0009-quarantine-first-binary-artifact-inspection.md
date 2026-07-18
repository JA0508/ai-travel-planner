# ADR-0009: Quarantine-First Binary Artifact Inspection

## Status

In review

## Date

2026-07-18

## Context

Import-to-Executable needs screenshots and PDFs, but binary artifacts are a
larger trust boundary than pasted text or bounded public URLs. A file upload
must not become OCR input, source text, a place candidate, or trip mutation
until it has passed deterministic intake gates.

## Decision

Image/PDF intake is quarantine-first:

```text
streamed multipart upload
→ staging file with running checksum and byte limit
→ content-based type detection
→ uploaded_image / uploaded_pdf SourceArtifact
→ binary ImportJob quarantined
→ isolated subprocess structural inspection
→ explicit findings
→ sanitized_image or document_manifest derivation
```

Supported formats are PDF, JPEG, PNG, and static WebP. The browser MIME type
and filename extension are only mismatch signals; the server uses magic bytes
and parser verification as the authority. Unsupported formats, executable
signatures, conflicting containers, and suspected polyglots are rejected before
inspection.

Uploads are streamed in bounded chunks. Original filenames are sanitized and
never used as storage paths. Staging and artifact directories are private, use
opaque server-generated names, and are cleaned up after processing.

Inspection runs in a subprocess with wall-clock timeout, bounded output, and
best-effort CPU/memory limits where the platform exposes them. The worker does
not receive database handles, trip capability, planner services, LLM clients, or
network adapters. Readiness reports whether wall-clock, memory, and CPU limits
are actually available on the current platform.

Images are inspected with Pillow 11.3.0, licensed under the HPND/Pillow license.
The worker verifies and fully decodes the file, enforces pixel/dimension/frame
limits, rejects animated images, detects metadata presence, normalizes
orientation, strips metadata, and writes a deterministic sanitized derivative.
The frontend displays only the sanitized derivative.

PDFs are inspected with pypdf 5.9.0, licensed BSD-3-Clause. The worker parses
the structure without executing JavaScript, opening attachments, rendering
pages, downloading resources, or exposing document metadata values. It records
page count, encryption, forms, XFA, actions, JavaScript, launch actions,
embedded files, rich media, external URI annotations, unusual page dimensions,
and object limits when available. Accepted PDFs produce a `document_manifest`
artifact, not a sanitized PDF and not an inline preview.

Findings are stable codes with severity, category, and privacy-safe evidence.
They are not scores and are not antivirus results. `artifact_ready` means the
artifact is accepted for future controlled extraction, not that it is harmless.

This slice intentionally does not perform OCR, PDF text extraction, image
captioning, place mention extraction, TripCandidate creation, TripRevision
creation, planner calls, mutation calls, inline PDF preview, or original binary
serving.

## Consequences

### Positive

- Future OCR can depend on a bounded, inspected, provenance-preserving artifact.
- Original binary bytes never have to be rendered or executed by the browser.
- Image previews are metadata-stripped derivatives with derivation lineage.
- PDF inspection produces reviewable structural facts without parsing text.
- Binary import remains outside the itinerary mutation domain.

### Negative / trade-offs

- Local file storage remains development-oriented and must be replaced by object
  storage for production scale.
- Resource limits vary by platform; memory limits are reported as degraded when
  not reliably available.
- pypdf structural detection is conservative and may not identify every hostile
  PDF construction.
- There is no password handling for encrypted PDFs.
- No OCR or mention extraction is available until F-002d.

## Related documents

- ADR-0007: Text Import Provenance and Review Boundary
- ADR-0008: Secure URL Import and Fetch Provenance
- Product phase: F-002c Image/PDF Artifact Intake and Safe Document Classification

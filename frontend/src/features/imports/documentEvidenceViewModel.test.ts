import assert from "node:assert/strict";
import test from "node:test";
import {
  buildDocumentEvidenceSummary,
  mapNormalizedBoxToOverlay,
  mentionEvidenceBoxes,
  toNormalizedDocumentBox,
} from "./documentEvidenceViewModel";
import type { DocumentExtractionEvidenceResponse } from "./importTypes";

test("maps normalized document boxes to stable overlay pixels", () => {
  const box = toNormalizedDocumentBox({
    x: 0.25,
    y: 0.1,
    width: 0.5,
    height: 0.2,
    origin: "top-left",
    unit: "normalized",
  });

  assert.ok(box);
  assert.deepEqual(mapNormalizedBoxToOverlay(box, { width: 800, height: 1000 }), {
    x: 0.25,
    y: 0.1,
    width: 0.5,
    height: 0.2,
    origin: "top-left",
    unit: "normalized",
    left: 200,
    top: 100,
    pixelWidth: 400,
    pixelHeight: 200,
  });
});

test("rejects incomplete, wrong-origin, and out-of-range document boxes", () => {
  assert.equal(toNormalizedDocumentBox({ x: 0, y: 0, width: 0.1, height: 0.1 }), null);
  assert.equal(
    toNormalizedDocumentBox({ x: 0, y: 0, width: 0.1, height: 0.1, origin: "bottom-left", unit: "normalized" }),
    null,
  );
  assert.equal(
    toNormalizedDocumentBox({ x: 0.95, y: 0.1, width: 0.1, height: 0.1, origin: "top-left", unit: "normalized" }),
    null,
  );
});

test("summarizes extraction evidence without treating missing geometry as proof", () => {
  const evidence = {
    generation: {
      id: "gen_1",
      trip_id: "trip_1",
      source_import_job_id: "job_source",
      source_artifact_id: "artifact_source",
      inspection_id: "inspection_1",
      derived_import_job_id: "job_doc",
      derived_artifact_id: "artifact_doc",
      layout_artifact_id: "layout_1",
      span_map_artifact_id: "spanmap_1",
      generation: 1,
      schema_version: "document-extraction-v1",
      extractor_version: "document-extractor-v1",
      strategy: "pdf_native_text",
      status: "review_ready",
      page_count: 2,
      extracted_text_chars: 42,
      warning_codes: [],
      error_code: null,
      metadata: {
        reading_order_algorithm: "layout-reading-order-v1",
        coordinate_space: "normalized-top-left",
      },
      created_at: "2026-07-20T00:00:00Z",
    },
    artifact: {
      id: "artifact_doc",
      trip_id: "trip_1",
      artifact_type: "derived_document_text",
      mime_type: "text/plain; charset=utf-8",
      content_checksum: "sha256:doc",
      byte_size: 42,
      charset: "utf-8",
      privacy_level: "private",
      created_at: "2026-07-20T00:00:00Z",
    },
    job: {
      id: "job_doc",
      trip_id: "trip_1",
      artifact_id: "artifact_doc",
      input_type: "document",
      status: "review_ready",
      extraction_schema_version: "text-import-v1",
      extractor_version: "document-extractor-v1",
      resolver_version: "place-resolver-v1",
      review_version: 1,
      mention_count: 2,
      warning_codes: [],
      error_code: null,
      created_at: "2026-07-20T00:00:00Z",
      updated_at: "2026-07-20T00:00:00Z",
    },
    layout_manifest: {},
    span_map: [{ span_start: 0 }, { span_start: 10 }],
    mentions: [
      minimalMention("mention_1", "外滩", 0, 2),
      minimalMention("mention_2", "备注", 10, 12),
    ],
    mention_evidence: [
      {
        mention_id: "mention_1",
        mention_text: "外滩",
        start_offset: 0,
        end_offset: 2,
        page_numbers: [1],
        block_ids: ["block_1"],
        line_ids: ["line_1"],
        token_ids: ["token_1"],
        bounding_boxes: [{ x: 0.1, y: 0.2, width: 0.3, height: 0.04, origin: "top-left", unit: "normalized" }],
        extraction_methods: ["native_pdf_text"],
        geometry_available: true,
      },
      {
        mention_id: "mention_2",
        mention_text: "备注",
        start_offset: 10,
        end_offset: 12,
        page_numbers: [],
        block_ids: [],
        line_ids: [],
        token_ids: [],
        bounding_boxes: [],
        extraction_methods: [],
        geometry_available: false,
      },
    ],
  } satisfies DocumentExtractionEvidenceResponse;

  assert.deepEqual(buildDocumentEvidenceSummary(evidence), {
    pageCount: 2,
    spanMapCount: 2,
    mentionCount: 2,
    geometryMentionCount: 1,
    methods: ["native_pdf_text"],
    layoutArtifactId: "layout_1",
    spanMapArtifactId: "spanmap_1",
    readingOrderAlgorithm: "layout-reading-order-v1",
    coordinateSpace: "normalized-top-left",
  });
  assert.equal(mentionEvidenceBoxes(evidence.mention_evidence[0]).length, 1);
  assert.equal(mentionEvidenceBoxes(evidence.mention_evidence[1]).length, 0);
});

function minimalMention(id: string, rawText: string, startOffset: number, endOffset: number) {
  return {
    id,
    import_job_id: "job_doc",
    artifact_id: "artifact_doc",
    entity_type: "place",
    raw_text: rawText,
    normalized_text: rawText,
    start_offset: startOffset,
    end_offset: endOffset,
    context_before: "",
    context_after: "",
    city_hint: null,
    date_hint: null,
    time_hint: null,
    recommendation_reason: null,
    confidence: 0.8,
    extraction_warning_codes: [],
    content_digest: `sha256:${id}`,
    review_state: "needs_review",
    selected_resolution_candidate_id: null,
    latest_decision: null,
    resolution_candidates: [],
    created_at: "2026-07-20T00:00:00Z",
  };
}

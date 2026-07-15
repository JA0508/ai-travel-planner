import assert from "node:assert/strict";
import test from "node:test";
import { buildImportSummary, selectedResolutionId, sourceSegments } from "./importViewModel";
import type { ImportMention } from "./importTypes";

test("source segments preserve exact active mention span", () => {
  const source = "第一天去豫园，然后去上海博物馆";
  const mention = mentionFixture({ raw_text: "上海博物馆", start_offset: 10, end_offset: 15 });
  const segments = sourceSegments(source, mention);
  assert.deepEqual(segments.map((segment) => segment.text), ["第一天去豫园，然后去", "上海博物馆"]);
  assert.equal(segments[1].active, true);
});

test("summary counts confirmed, ignored, unresolved, and preserved non-place mentions", () => {
  const summary = buildImportSummary([
    mentionFixture({ review_state: "confirmed" }),
    mentionFixture({ id: "m2", review_state: "ignored" }),
    mentionFixture({ id: "m3", review_state: "unresolved" }),
    mentionFixture({ id: "m4", entity_type: "fixed_event" }),
  ]);
  assert.equal(summary.confirmedCount, 1);
  assert.equal(summary.ignoredCount, 1);
  assert.equal(summary.unresolvedCount, 1);
  assert.equal(summary.preservedContextCount, 1);
});

test("selected resolution ignores missing/provider failed candidates", () => {
  const mention = mentionFixture({
    resolution_candidates: [
      {
        id: "missing",
        mention_id: "m1",
        provider: "local",
        canonical_name: "missing",
        confidence: 1,
        resolution_reason_codes: [],
        data_state: "missing",
        candidate_digest: "a",
        created_at: "now",
      },
      {
        id: "resolved",
        mention_id: "m1",
        provider: "local",
        canonical_name: "豫园",
        confidence: 0.9,
        resolution_reason_codes: [],
        data_state: "resolved",
        candidate_digest: "b",
        created_at: "now",
      },
    ],
  });
  assert.equal(selectedResolutionId(mention), "resolved");
});

function mentionFixture(overrides: Partial<ImportMention> = {}): ImportMention {
  return {
    id: "m1",
    import_job_id: "imp_1",
    artifact_id: "src_1",
    entity_type: "place",
    raw_text: "豫园",
    start_offset: 4,
    end_offset: 6,
    context_before: "",
    context_after: "",
    confidence: 0.9,
    extraction_warning_codes: [],
    content_digest: "digest",
    review_state: "needs_review",
    resolution_candidates: [],
    created_at: "now",
    ...overrides,
  };
}

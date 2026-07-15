import assert from "node:assert/strict";
import test from "node:test";
import { importIdempotencyKey, importWorkspaceReducer } from "./importState";

test("import workspace reducer keeps a single discriminated state owner", () => {
  const submitting = importWorkspaceReducer({ status: "idle" }, { type: "submit" });
  assert.equal(submitting.status, "submitting");

  const review = importWorkspaceReducer(submitting, {
    type: "review",
    artifact: {
      id: "src_1",
      trip_id: "trip_1",
      artifact_type: "text",
      mime_type: "text/plain",
      content_checksum: "abc",
      byte_size: 12,
      charset: "utf-8",
      privacy_level: "private",
      created_at: "now",
    },
    job: {
      id: "imp_1",
      trip_id: "trip_1",
      artifact_id: "src_1",
      input_type: "text",
      status: "review_ready",
      extraction_schema_version: "1.0",
      extractor_version: "deterministic",
      resolver_version: "deterministic",
      review_version: 2,
      mention_count: 1,
      warning_codes: [],
      created_at: "now",
      updated_at: "now",
    },
    sourceText: "景点：豫园",
    mentions: [
      {
        id: "men_1",
        import_job_id: "imp_1",
        artifact_id: "src_1",
        entity_type: "place",
        raw_text: "豫园",
        start_offset: 3,
        end_offset: 5,
        context_before: "景点：",
        context_after: "",
        confidence: 0.9,
        extraction_warning_codes: [],
        content_digest: "digest",
        review_state: "needs_review",
        resolution_candidates: [],
        created_at: "now",
      },
    ],
  });
  assert.equal(review.status, "reviewing");
  assert.equal(review.activeMentionId, "men_1");
  assert.equal(review.reviewVersion, 2);
});

test("idempotency key is deterministic and bounded", () => {
  const first = importIdempotencyKey("import", "trip_1", "same");
  const second = importIdempotencyKey("import", "trip_1", "same");
  assert.equal(first, second);
  assert.ok(first.length <= 180);
});

test("idempotency key is safe for browser headers and does not leak raw source text", () => {
  const key = importIdempotencyKey(
    "text-import",
    "trip_1",
    "135:攻略摘录：上午可以去豫园，下午考虑外滩，晚上南京路步行街。",
  );

  assert.match(key, /^[\x20-\x7E]+$/);
  assert.equal(key.includes("豫园"), false);
  assert.equal(key.includes("攻略摘录"), false);
});

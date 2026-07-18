import assert from "node:assert/strict";
import test from "node:test";
import {
  binaryImportIdempotencyKey,
  binaryImportKindForFile,
  binaryImportReducer,
  binaryImportStorageValue,
  parseBinaryImportStorageValue,
} from "./binaryImportState";

test("binary import reducer keeps one discriminated state owner", () => {
  const file = new File(["abc"], "private-guide.png", { type: "image/png" });
  const selected = binaryImportReducer({ status: "idle" }, { type: "select", file, declaredKind: "image" });
  assert.equal(selected.status, "selected");
  assert.equal(selected.displayName.includes("private-guide"), false);

  const ready = binaryImportReducer({ status: "uploading" }, {
    type: "uploaded",
    artifact: {
      id: "src_1",
      trip_id: "trip_1",
      artifact_type: "uploaded_image",
      mime_type: "image/png",
      content_checksum: "checksum",
      byte_size: 3,
      charset: "binary",
      privacy_level: "private",
      created_at: "now",
    },
    job: {
      id: "imp_1",
      trip_id: "trip_1",
      artifact_id: "src_1",
      input_type: "image",
      status: "artifact_ready",
      extraction_schema_version: "1.0",
      extractor_version: "binary-inspector-v1",
      resolver_version: "none",
      review_version: 0,
      mention_count: 0,
      warning_codes: [],
      created_at: "now",
      updated_at: "now",
    },
    inspection: {
      id: "art_ins_1",
      trip_id: "trip_1",
      import_job_id: "imp_1",
      artifact_id: "src_1",
      attempt: 1,
      schema_version: "1.0",
      inspector_version: "binary-inspector-v1",
      declared_kind: "image",
      detected_kind: "image",
      detected_mime_type: "image/png",
      status: "artifact_ready",
      classification: "artifact_ready",
      byte_size: 3,
      content_checksum: "checksum",
      metadata: {},
      findings: [],
      warning_codes: [],
      started_at: "now",
      completed_at: "now",
    },
  });
  assert.equal(ready.status, "artifact_ready");
});

test("binary file kind accepts only PDF JPEG PNG and WebP", () => {
  assert.equal(binaryImportKindForFile(new File(["x"], "a.pdf", { type: "application/pdf" })), "pdf");
  assert.equal(binaryImportKindForFile(new File(["x"], "a.jpg", { type: "image/jpeg" })), "image");
  assert.equal(binaryImportKindForFile(new File(["x"], "a.png", { type: "image/png" })), "image");
  assert.equal(binaryImportKindForFile(new File(["x"], "a.webp", { type: "image/webp" })), "image");
  assert.equal(binaryImportKindForFile(new File(["x"], "a.gif", { type: "image/gif" })), null);
  assert.equal(binaryImportKindForFile(new File(["x"], "a.docx", { type: "application/vnd.openxmlformats-officedocument.wordprocessingml.document" })), null);
});

test("binary idempotency key is ascii and does not include original filename", () => {
  const file = new File(["abc"], "私密攻略-外滩.png", { type: "image/png" });
  const key = binaryImportIdempotencyKey("trip_1", file, "image");
  assert.match(key, /^[\x20-\x7E]+$/);
  assert.equal(key.includes("私密攻略"), false);
  assert.equal(key.includes("外滩"), false);
  assert.equal(key.includes(".png"), false);
});

test("binary localStorage value stores only minimal trip and job reference", () => {
  const raw = binaryImportStorageValue("trip_1", "imp_1", "pdf");
  assert.equal(raw.includes("private-guide"), false);
  assert.equal(raw.includes("base64"), false);
  assert.equal(raw.includes("data:"), false);
  assert.deepEqual(parseBinaryImportStorageValue(raw), { tripId: "trip_1", jobId: "imp_1", declaredKind: "pdf" });
});

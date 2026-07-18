import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import test from "node:test";

const componentPath = fileURLToPath(new URL("./ImportReviewWorkspace.tsx", import.meta.url));
const binaryResultPath = fileURLToPath(new URL("./BinaryInspectionResult.tsx", import.meta.url));
const binaryStatePath = fileURLToPath(new URL("./binaryImportState.ts", import.meta.url));

test("url import workspace does not add iframe or raw html rendering paths", () => {
  const source = readFileSync(componentPath, "utf-8") + readFileSync(binaryResultPath, "utf-8");
  assert.equal(source.includes("<iframe"), false);
  assert.equal(source.includes("<embed"), false);
  assert.equal(source.includes("<object"), false);
  assert.equal(source.includes("dangerouslySetInnerHTML"), false);
  assert.match(source, /rel="noopener noreferrer"/);
  assert.match(source, /target="_blank"/);
});

test("binary import UI uses sanitized endpoint blob URLs and never original file object URLs", () => {
  const source = readFileSync(componentPath, "utf-8");
  assert.match(source, /fetchSanitizedImageBlob/);
  assert.match(source, /URL\.revokeObjectURL/);
  assert.equal(source.includes("URL.createObjectURL(binaryState.file"), false);
  assert.equal(source.includes("readAsDataURL"), false);
});

test("binary import persistence avoids bytes base64 metadata payloads and filenames", () => {
  const stateSource = readFileSync(binaryStatePath, "utf-8");
  assert.match(stateSource, /binaryImportStorageValue/);
  assert.equal(stateSource.includes("base64"), false);
  assert.equal(stateSource.includes("content_checksum"), false);
  assert.equal(stateSource.includes("metadata"), false);
});

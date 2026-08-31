import assert from "node:assert/strict";
import test from "node:test";

import {
  buildImportCapabilityViewModel,
  importFormReasonMessage,
} from "./importCapabilityViewModel";
import type { ImportCapabilityPack } from "./importTypes";

const snapshot: ImportCapabilityPack = {
  schema_version: "1.0",
  forms: [
    { form: "text", availability: "available", reason_codes: [], processing_stages: [], safety_boundary_codes: [] },
    { form: "url", availability: "unavailable", reason_codes: ["url_import_disabled"], processing_stages: [], safety_boundary_codes: [] },
    { form: "image", availability: "degraded", reason_codes: ["ocr_unavailable"], processing_stages: [], safety_boundary_codes: [] },
    { form: "pdf", availability: "unavailable", reason_codes: ["binary_inspection_unavailable"], processing_stages: [], safety_boundary_codes: [] },
  ],
};

test("capability view model disables only server-unavailable forms and preserves degraded warnings", () => {
  const model = buildImportCapabilityViewModel({ status: "ready", snapshot });

  assert.equal(model.forms.text.disabled, false);
  assert.equal(model.forms.url.disabled, true);
  assert.equal(model.forms.image.disabled, false);
  assert.equal(model.forms.image.availabilityLabel, "Limited");
  assert.deepEqual(model.forms.image.reasonMessages, ["Text recognition is unavailable; image extraction may be partial."]);
  assert.equal(model.forms.pdf.disabled, true);
});

test("capability loading and recoverable errors do not preemptively disable safe server-validated intake", () => {
  const loading = buildImportCapabilityViewModel({ status: "loading" });
  const failed = buildImportCapabilityViewModel({
    status: "error",
    code: "trip_access_denied",
    message: "Capability check failed.",
  });

  assert.equal(loading.statusMessage, "Checking available import methods…");
  assert.equal(loading.forms.text.disabled, false);
  assert.equal(loading.forms.pdf.disabled, true);
  assert.equal(failed.statusMessage, "Import availability could not be verified. Text and URL import remain available; retry before uploading images or PDFs.");
  assert.equal(failed.forms.url.disabled, false);
  assert.equal(failed.forms.pdf.disabled, true);
});

test("missing capability forms stay disabled instead of implying support", () => {
  const model = buildImportCapabilityViewModel({
    status: "ready",
    snapshot: {
      schema_version: "1.0",
      forms: [
        { form: "text", availability: "available", reason_codes: [], processing_stages: [], safety_boundary_codes: [] },
        { form: "url", availability: "available", reason_codes: [], processing_stages: [], safety_boundary_codes: [] },
      ],
    },
  });

  assert.equal(model.forms.text.disabled, false);
  assert.equal(model.forms.url.disabled, false);
  assert.equal(model.forms.image.disabled, true);
  assert.equal(model.forms.pdf.disabled, true);
});

test("capability reason messages are stable user-facing explanations without runtime details", () => {
  assert.equal(importFormReasonMessage("pdf_renderer_unavailable"), "PDF page rendering is unavailable; document extraction may be partial.");
  assert.equal(importFormReasonMessage("unknown_reason"), "This import method is currently limited by server safeguards.");
});

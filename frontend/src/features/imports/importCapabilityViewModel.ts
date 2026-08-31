import type { ImportCapabilityState } from "./importState";
import type { ImportCapabilityAvailability, ImportForm, ImportFormCapability } from "./importTypes";

const FORM_ORDER: ImportForm[] = ["text", "url", "image", "pdf"];

type ImportFormCapabilityView = {
  availability: ImportCapabilityAvailability | "unknown";
  availabilityLabel: string;
  disabled: boolean;
  reasonCodes: string[];
  reasonMessages: string[];
};

export type ImportCapabilityViewModel = {
  statusMessage: string | null;
  forms: Record<ImportForm, ImportFormCapabilityView>;
};

export function buildImportCapabilityViewModel(state: ImportCapabilityState): ImportCapabilityViewModel {
  if (state.status === "loading") {
    return { statusMessage: "Checking available import methods…", forms: fallbackForms("checking") };
  }
  if (state.status === "error") {
    return {
      statusMessage: "Import availability could not be verified. Text and URL import remain available; retry before uploading images or PDFs.",
      forms: fallbackForms("error"),
    };
  }
  if (state.status !== "ready") {
    return { statusMessage: null, forms: fallbackForms("idle") };
  }

  return {
    statusMessage: null,
    forms: Object.fromEntries(
      FORM_ORDER.map((form) => [form, formView(state.snapshot.forms.find((item) => item.form === form))]),
    ) as Record<ImportForm, ImportFormCapabilityView>,
  };
}

export function importFormReasonMessage(reasonCode: string): string {
  switch (reasonCode) {
    case "text_import_disabled":
      return "Text import is temporarily disabled by the server.";
    case "url_import_disabled":
      return "URL import is temporarily disabled by the server.";
    case "binary_import_disabled":
      return "Image and PDF uploads are temporarily disabled by the server.";
    case "binary_inspection_unavailable":
      return "Binary inspection is unavailable, so uploads cannot be accepted safely.";
    case "document_extraction_disabled":
      return "Document extraction is disabled; uploaded documents may remain inspection-only.";
    case "ocr_unavailable":
      return "Text recognition is unavailable; image extraction may be partial.";
    case "pdf_renderer_unavailable":
      return "PDF page rendering is unavailable; document extraction may be partial.";
    default:
      return "This import method is currently limited by server safeguards.";
  }
}

function fallbackForms(reason: "checking" | "error" | "idle"): Record<ImportForm, ImportFormCapabilityView> {
  const textLike = (): ImportFormCapabilityView => ({
    availability: "unknown",
    availabilityLabel: reason === "checking" ? "Checking" : "Fallback",
    disabled: false,
    reasonCodes: [],
    reasonMessages: [],
  });
  const binary = (): ImportFormCapabilityView => ({
    availability: "unknown",
    availabilityLabel: reason === "checking" ? "Checking" : "Unavailable to verify",
    disabled: true,
    reasonCodes: [reason === "checking" ? "capability_check_pending" : "capability_check_failed"],
    reasonMessages: ["Retry availability before uploading files."],
  });
  return {
    text: textLike(),
    url: textLike(),
    image: binary(),
    pdf: binary(),
  };
}

function formView(capability: ImportFormCapability | undefined): ImportFormCapabilityView {
  if (!capability) {
    return {
      availability: "unknown",
      availabilityLabel: "Unavailable to verify",
      disabled: true,
      reasonCodes: ["capability_form_missing"],
      reasonMessages: ["Retry availability before using this import method."],
    };
  }
  return {
    availability: capability.availability,
    availabilityLabel: capability.availability === "available" ? "Available" : capability.availability === "degraded" ? "Limited" : "Unavailable",
    disabled: capability.availability === "unavailable",
    reasonCodes: capability.reason_codes,
    reasonMessages: capability.reason_codes.map(importFormReasonMessage),
  };
}

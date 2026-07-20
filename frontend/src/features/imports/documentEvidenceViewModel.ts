import type { DocumentExtractionEvidenceResponse, DocumentMentionEvidence } from "./importTypes";

export type NormalizedDocumentBox = {
  x: number;
  y: number;
  width: number;
  height: number;
  origin: "top-left";
  unit: "normalized";
};

export type OverlayDocumentBox = NormalizedDocumentBox & {
  left: number;
  top: number;
  pixelWidth: number;
  pixelHeight: number;
};

export type DocumentEvidenceSummary = {
  pageCount: number;
  spanMapCount: number;
  mentionCount: number;
  geometryMentionCount: number;
  methods: string[];
  layoutArtifactId: string | null;
  spanMapArtifactId: string | null;
  readingOrderAlgorithm: string | null;
  coordinateSpace: string | null;
};

export function toNormalizedDocumentBox(value: Record<string, unknown>): NormalizedDocumentBox | null {
  const x = finiteNumber(value.x);
  const y = finiteNumber(value.y);
  const width = finiteNumber(value.width);
  const height = finiteNumber(value.height);
  if (x === null || y === null || width === null || height === null) {
    return null;
  }
  if (value.origin !== "top-left" || value.unit !== "normalized") {
    return null;
  }
  if (width <= 0 || height <= 0 || x < 0 || y < 0 || x + width > 1 || y + height > 1) {
    return null;
  }
  return { x, y, width, height, origin: "top-left", unit: "normalized" };
}

export function mapNormalizedBoxToOverlay(
  box: NormalizedDocumentBox,
  surface: { width: number; height: number },
): OverlayDocumentBox {
  return {
    ...box,
    left: roundPixel(box.x * surface.width),
    top: roundPixel(box.y * surface.height),
    pixelWidth: roundPixel(box.width * surface.width),
    pixelHeight: roundPixel(box.height * surface.height),
  };
}

export function buildDocumentEvidenceSummary(
  evidence: DocumentExtractionEvidenceResponse | null,
): DocumentEvidenceSummary | null {
  if (!evidence) {
    return null;
  }
  const methods = Array.from(
    new Set(evidence.mention_evidence.flatMap((mention) => mention.extraction_methods)),
  ).sort();
  const metadata = evidence.generation.metadata;
  return {
    pageCount: evidence.generation.page_count,
    spanMapCount: evidence.span_map.length,
    mentionCount: evidence.mentions.length,
    geometryMentionCount: evidence.mention_evidence.filter((mention) => mention.geometry_available).length,
    methods,
    layoutArtifactId: evidence.generation.layout_artifact_id ?? null,
    spanMapArtifactId: evidence.generation.span_map_artifact_id ?? null,
    readingOrderAlgorithm: stringValue(metadata.reading_order_algorithm),
    coordinateSpace: stringValue(metadata.coordinate_space),
  };
}

export function mentionEvidenceBoxes(mention: DocumentMentionEvidence): NormalizedDocumentBox[] {
  return mention.bounding_boxes.flatMap((box) => {
    const normalized = toNormalizedDocumentBox(box);
    return normalized ? [normalized] : [];
  });
}

function finiteNumber(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

function stringValue(value: unknown): string | null {
  return typeof value === "string" && value.trim() ? value : null;
}

function roundPixel(value: number): number {
  return Math.round(value * 100) / 100;
}

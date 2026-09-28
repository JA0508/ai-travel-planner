const PREVIEW_REVEAL_TOP_GUTTER_PX = 24;

export function previewRevealScrollTop(
  target: Pick<DOMRect, "top">,
  currentScrollY: number,
): number {
  const safeCurrentScrollY = Number.isFinite(currentScrollY) ? Math.max(0, currentScrollY) : 0;
  const safeTargetTop = Number.isFinite(target.top) ? target.top : 0;
  return Math.max(0, Math.round(safeCurrentScrollY + safeTargetTop - PREVIEW_REVEAL_TOP_GUTTER_PX));
}

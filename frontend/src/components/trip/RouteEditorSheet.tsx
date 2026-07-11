"use client";

import {
  CSSProperties,
  PointerEvent as ReactPointerEvent,
  ReactNode,
  useEffect,
  useRef,
  useState,
} from "react";

export type RouteEditorSheetSnap = 30 | 68 | 96;

type RouteEditorSheetProps = {
  children: ReactNode;
  snap?: RouteEditorSheetSnap;
  onSnapChange?: (snap: RouteEditorSheetSnap) => void;
  className?: string;
};

const SNAP_POINTS: RouteEditorSheetSnap[] = [30, 68, 96];

export function RouteEditorSheet({
  children,
  snap = 68,
  onSnapChange,
  className,
}: RouteEditorSheetProps) {
  const [localSnap, setLocalSnap] = useState<RouteEditorSheetSnap>(snap);
  const dragStartRef = useRef<{ y: number; snap: RouteEditorSheetSnap } | null>(null);

  useEffect(() => {
    setLocalSnap(snap);
  }, [snap]);

  const commitSnap = (nextSnap: RouteEditorSheetSnap) => {
    setLocalSnap(nextSnap);
    onSnapChange?.(nextSnap);
  };

  const handlePointerMove = (event: ReactPointerEvent<HTMLDivElement>) => {
    if (!dragStartRef.current) {
      return;
    }
    const viewportHeight = window.innerHeight || 1;
    const deltaPercent = ((dragStartRef.current.y - event.clientY) / viewportHeight) * 100;
    const rawSnap = dragStartRef.current.snap + deltaPercent;
    const clampedSnap = Math.max(30, Math.min(96, rawSnap));
    setLocalSnap(clampedSnap as RouteEditorSheetSnap);
  };

  const handlePointerUp = () => {
    if (!dragStartRef.current) {
      return;
    }
    const nearestSnap = SNAP_POINTS.reduce((closest, candidate) =>
      Math.abs(candidate - localSnap) < Math.abs(closest - localSnap) ? candidate : closest,
    );
    dragStartRef.current = null;
    commitSnap(nearestSnap);
  };

  return (
    <section
      className={className}
      style={{
        ...sheetStyle,
        height: `${localSnap}dvh`,
      }}
    >
      <div
        role="presentation"
        onPointerDown={(event) => {
          event.currentTarget.setPointerCapture(event.pointerId);
          dragStartRef.current = { y: event.clientY, snap: localSnap };
        }}
        onPointerMove={handlePointerMove}
        onPointerUp={handlePointerUp}
        onPointerCancel={handlePointerUp}
        style={handleZoneStyle}
      >
        <span style={handleStyle} />
      </div>
      <div style={contentStyle}>{children}</div>
    </section>
  );
}

const sheetStyle: CSSProperties = {
  position: "absolute",
  right: 0,
  bottom: 0,
  left: 0,
  zIndex: 3,
  display: "grid",
  gridTemplateRows: "36px minmax(0, 1fr)",
  overflow: "hidden",
  borderRadius: "34px 34px 0 0",
  background:
    "radial-gradient(circle at top left, rgba(239,229,214,0.38), transparent 32%), linear-gradient(180deg, rgba(255,253,249,0.98), rgba(247,244,238,0.96))",
  border: "1px solid var(--ec-line)",
  boxShadow: "0 -28px 68px rgba(21, 21, 21, 0.16)",
  backdropFilter: "blur(18px)",
  transition: "height 220ms cubic-bezier(0.22, 1, 0.36, 1)",
};

const handleZoneStyle: CSSProperties = {
  display: "grid",
  placeItems: "center",
  touchAction: "none",
  cursor: "ns-resize",
};

const handleStyle: CSSProperties = {
  width: 52,
  height: 5,
  borderRadius: 999,
  background: "linear-gradient(90deg, rgba(37,99,235,0.54), rgba(147,197,253,0.72))",
};

const contentStyle: CSSProperties = {
  minHeight: 0,
  overflowY: "auto",
  overscrollBehavior: "contain",
  padding: "4px 20px 28px",
};

"use client";

import { ReactNode } from "react";

export type DayTimelineBlockViewModel = {
  key: string;
  title: string;
  timeRangeLabel: string;
  explanation: string;
  backgroundColor: string;
  borderColor: string;
  stops: ReactNode[];
};

export type DayTimelineDayViewModel = {
  key: string;
  dayLabel: string;
  availabilityLabel: string;
  remainingBlocksLabel?: string;
  blocks: DayTimelineBlockViewModel[];
};

export function DayTimeline({
  days,
}: {
  days: DayTimelineDayViewModel[];
}) {
  return (
    <>
      {days.map((day) => (
        <section
          key={day.key}
          className="day-timeline__day"
          style={{
            position: "relative",
            overflow: "hidden",
            border: "1px solid var(--ec-line)",
            borderRadius: 32,
            padding: 26,
            background:
              "linear-gradient(180deg, rgba(255,253,249,0.99) 0%, rgba(248,250,252,0.9) 100%)",
            boxShadow: "var(--ec-shadow-2)",
            display: "grid",
            gap: 22,
          }}
        >
          <div
            style={{
              position: "relative",
              overflow: "hidden",
              display: "flex",
              justifyContent: "space-between",
              gap: 16,
              alignItems: "flex-end",
              flexWrap: "wrap",
              padding: "18px 20px",
              borderRadius: 28,
              background:
                "linear-gradient(135deg, rgba(239,246,255,0.9) 0%, rgba(255,253,249,0.88) 58%, rgba(239,229,214,0.34) 100%)",
              border: "1px solid rgba(37, 99, 235, 0.14)",
            }}
          >
            <span
              aria-hidden="true"
              style={{
                position: "absolute",
                left: 20,
                right: "42%",
                top: 0,
                height: 4,
                borderRadius: "0 0 999px 999px",
                background: "var(--ec-route-blue)",
              }}
            />
            <div style={{ display: "grid", gap: 4 }}>
              <h3
                style={{
                  margin: 0,
                  fontFamily: '"Iowan Old Style", Georgia, "Times New Roman", serif',
                  fontSize: 34,
                  letterSpacing: "-0.045em",
                  lineHeight: 0.95,
                  color: "var(--ec-ink)",
                }}
              >
                {day.dayLabel}
              </h3>
              <p
                style={{
                  margin: 0,
                  color: "var(--ec-slate)",
                  fontSize: 14,
                  fontWeight: 800,
                }}
              >
                {day.availabilityLabel}
              </p>
            </div>
            {day.remainingBlocksLabel ? (
              <div
                style={{
                  padding: "9px 13px",
                  borderRadius: 999,
                  backgroundColor: "rgba(255,255,255,0.88)",
                  border: "1px solid rgba(37,99,235,0.12)",
                  color: "var(--ec-ink)",
                  fontSize: 12,
                  fontWeight: 900,
                  letterSpacing: "0.04em",
                }}
              >
                {day.remainingBlocksLabel}
              </div>
            ) : null}
          </div>

          <div
            style={{
              position: "relative",
              display: "grid",
              gap: 18,
              paddingLeft: 18,
            }}
          >
            <div
              aria-hidden="true"
              style={{
                position: "absolute",
                top: 8,
                bottom: 8,
                left: 4,
                width: 3,
                borderRadius: 999,
                background:
                  "linear-gradient(180deg, rgba(37,99,235,0.96) 0%, rgba(125,167,229,0.72) 48%, rgba(177,138,88,0.72) 100%)",
              }}
            />
            {day.blocks.map((block) => (
              <section
                key={block.key}
                className="day-timeline__block"
                style={{
                  position: "relative",
                  display: "grid",
                  gridTemplateColumns: "minmax(132px, 0.54fr) minmax(0, 1.46fr)",
                  gap: 18,
                  alignItems: "start",
                  borderRadius: 26,
                  padding: 18,
                  background:
                    "linear-gradient(135deg, rgba(255,255,255,0.9), rgba(248,250,252,0.74))",
                  border: `1px solid ${block.borderColor}`,
                  boxShadow:
                    "inset 0 1px 0 rgba(255,255,255,0.72), 0 16px 38px rgba(15,23,42,0.04)",
                }}
              >
                <span
                  aria-hidden="true"
                  style={{
                    position: "absolute",
                    top: 22,
                    left: -24,
                    width: 14,
                    height: 14,
                    borderRadius: 999,
                    background: "var(--ec-paper-strong)",
                    border: "3px solid var(--ec-route-blue)",
                    boxShadow: "0 0 0 6px rgba(37,99,235,0.08)",
                  }}
                />
                <div style={{ display: "grid", gap: 10 }}>
                  <div
                    style={{
                      display: "grid",
                      gap: 12,
                    }}
                  >
                    <span
                      style={{
                        width: "fit-content",
                        color: "var(--ec-route-blue)",
                        fontSize: 12,
                        fontWeight: 950,
                        letterSpacing: "0.08em",
                        textTransform: "uppercase",
                      }}
                    >
                      {block.timeRangeLabel}
                    </span>
                    <h4
                      style={{
                        margin: 0,
                        color: "var(--ec-ink)",
                        fontSize: 19,
                        lineHeight: 1.1,
                        letterSpacing: "-0.025em",
                      }}
                    >
                      {block.title}
                    </h4>
                  </div>
                  <p
                    style={{
                      margin: 0,
                      color: "var(--ec-slate)",
                      fontSize: 14,
                      lineHeight: 1.65,
                    }}
                  >
                    {block.explanation}
                  </p>
                </div>

                {block.stops.length > 0 ? (
                  <div style={{ display: "grid", gap: 12 }}>{block.stops}</div>
                ) : (
                  <div
                    style={{
                      borderRadius: 18,
                      padding: "16px 18px",
                      background:
                        "linear-gradient(135deg, rgba(239,246,255,0.74), rgba(255,255,255,0.84))",
                      border: "1px dashed rgba(37,99,235,0.22)",
                      color: "var(--ec-slate)",
                      fontSize: 14,
                      lineHeight: 1.58,
                    }}
                  >
                    这个时段还没有安排，适合从补全任务里补一个轻量地点。
                  </div>
                )}
              </section>
            ))}
          </div>

        </section>
      ))}
      <style>{`
        @media (max-width: 760px) {
          .day-timeline__block {
            grid-template-columns: 1fr !important;
          }
        }
      `}</style>
    </>
  );
}

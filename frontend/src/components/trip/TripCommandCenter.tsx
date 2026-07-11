"use client";

export type TripCommandCenterSignal = {
  label: string;
  value: string;
  tone: "ink" | "moss" | "ochre" | "paper";
};

export type TripCommandCenterAction = {
  label: string;
  description: string;
  onClick: () => void;
  primary?: boolean;
};

export type TripCommandCenterProps = {
  city: string;
  tripDays: number;
  completeness: number | null;
  statusLabel: string;
  statusTone: "stable" | "attention";
  headline: string;
  sparseBlockCount: number;
  autoFilledCount: number;
  pendingTaskCount: number;
  stayLabel: string | null;
  departureLabel: string | null;
  weakestDay?: {
    day: number;
    reason: string;
  } | null;
  intentLines: string[];
  systemLines: string[];
  actions: TripCommandCenterAction[];
};

export function TripCommandCenter({
  actions,
  autoFilledCount,
  city,
  completeness,
  departureLabel,
  headline,
  intentLines,
  pendingTaskCount,
  sparseBlockCount,
  statusLabel,
  statusTone,
  stayLabel,
  systemLines,
  tripDays,
  weakestDay,
}: TripCommandCenterProps) {
  const primaryAction = actions.find((action) => action.primary) ?? actions[0] ?? null;
  const signals: TripCommandCenterSignal[] = [
    {
      label: "完整度",
      value: completeness == null ? "--" : `${completeness}%`,
      tone: completeness == null ? "paper" : completeness >= 82 ? "moss" : "ochre",
    },
    {
      label: "待修复",
      value: `${pendingTaskCount}`,
      tone: pendingTaskCount > 0 ? "ochre" : "moss",
    },
    {
      label: "空缺",
      value: `${sparseBlockCount}`,
      tone: sparseBlockCount > 0 ? "ochre" : "moss",
    },
  ];
  const routeFactLine = [
    stayLabel ? `住：${stayLabel}` : null,
    departureLabel ? `离：${departureLabel}` : null,
    autoFilledCount > 0 ? `已补入 ${autoFilledCount} 个点` : null,
  ].filter(Boolean).join(" · ");

  return (
    <section className="trip-command-center" aria-label="路线状态">
      <div className="trip-command-center__mapline" aria-hidden="true">
        <span />
        <span />
        <span />
      </div>

      <div className="trip-command-center__header">
        <div className="trip-command-center__kicker">
          <span>路线状态</span>
          <span>{city}</span>
          <span>{tripDays} 天</span>
        </div>
        <div className="trip-command-center__title-row">
          <h3>路线状态</h3>
          <span
            className={`trip-command-center__status trip-command-center__status--${statusTone}`}
          >
            {statusLabel}
          </span>
        </div>
        <p>{headline}</p>
      </div>

      <div className="trip-command-center__signals">
        {signals.map((signal) => (
          <MetricTile key={signal.label} signal={signal} />
        ))}
      </div>

      {weakestDay ? (
        <div className="trip-command-center__focus">
          <span>下一步</span>
          <strong>先处理第 {weakestDay.day} 天</strong>
          <p>{weakestDay.reason}</p>
        </div>
      ) : (
        <div className="trip-command-center__focus trip-command-center__focus--quiet">
          <span>下一步</span>
          <strong>路线已经可以先看一遍</strong>
          <p>如果时间、距离和节奏都合理，可以再进入地点详情做小范围替换。</p>
        </div>
      )}

      {routeFactLine ? <p className="trip-command-center__route-facts">{routeFactLine}</p> : null}

      {primaryAction ? (
        <div className="trip-command-center__actions">
          <button
            type="button"
            onClick={primaryAction.onClick}
            className="trip-command-center__action trip-command-center__action--primary"
          >
            <strong>{primaryAction.label}</strong>
            <span>{primaryAction.description}</span>
          </button>
        </div>
      ) : null}

      <details className="trip-command-center__ledger" aria-label="路线依据摘要">
        <summary>查看系统依据</summary>
        <div>
          <span>已理解</span>
          <strong>已保护的边界</strong>
          <p>{intentLines[0] ?? "已识别目的地、天数、偏好和固定安排，先保护这些输入。"}</p>
        </div>
        <div>
          <span>已检查</span>
          <strong>下一步风险</strong>
          <p>{systemLines[0] ?? "已按时间、路线和空档检查当前计划，待补项会被拆成可操作任务。"}</p>
        </div>
      </details>

      <style>{`
        .trip-command-center {
          position: relative;
          overflow: hidden;
          display: grid;
          gap: 9px;
          padding: 14px;
          border-radius: 26px;
          background:
            radial-gradient(circle at 96% 4%, rgba(37, 99, 235, 0.1), transparent 25%),
            radial-gradient(circle at 0% 100%, rgba(102, 113, 95, 0.1), transparent 28%),
            linear-gradient(180deg, rgba(255, 253, 249, 0.99) 0%, rgba(247, 244, 238, 0.92) 100%);
          border: 1px solid rgba(37,99,235,0.10);
          box-shadow: var(--ec-shadow-1);
          isolation: isolate;
        }

        .trip-command-center::before {
          content: "";
          position: absolute;
          inset: 0;
          z-index: -2;
          background:
            linear-gradient(90deg, rgba(21, 21, 21, 0.026) 1px, transparent 1px),
            linear-gradient(180deg, rgba(21, 21, 21, 0.026) 1px, transparent 1px);
          background-size: 28px 28px;
          mask-image: linear-gradient(180deg, black 0%, transparent 88%);
        }

        .trip-command-center__mapline {
          position: absolute;
          top: 16px;
          right: 14px;
          width: 74px;
          height: 46px;
          opacity: 0.22;
          pointer-events: none;
        }

        .trip-command-center__mapline::before {
          content: "";
          position: absolute;
          inset: 19px 4px auto 4px;
          height: 2px;
          border-top: 2px dashed rgba(37, 99, 235, 0.72);
          transform: rotate(-8deg);
        }

        .trip-command-center__mapline span {
          position: absolute;
          width: 10px;
          height: 10px;
          border-radius: 999px;
          background: var(--ec-paper-strong);
          border: 2px solid #2563eb;
        }

        .trip-command-center__mapline span:nth-child(1) {
          left: 2px;
          top: 25px;
          background: #2563eb;
        }

        .trip-command-center__mapline span:nth-child(2) {
          left: 54px;
          top: 16px;
        }

        .trip-command-center__mapline span:nth-child(3) {
          right: 0;
          top: 8px;
          border-color: #93c5fd;
        }

        .trip-command-center__header {
          display: grid;
          gap: 5px;
          padding-right: 34px;
        }

        .trip-command-center__kicker {
          display: flex;
          flex-wrap: wrap;
          gap: 6px;
          color: var(--ec-slate);
          font-size: 10px;
          font-weight: 900;
          letter-spacing: 0.12em;
          text-transform: uppercase;
        }

        .trip-command-center__kicker span {
          padding: 5px 8px;
          border-radius: 999px;
          background: rgba(255, 253, 249, 0.72);
          border: 1px solid var(--ec-line-soft);
        }

        .trip-command-center__title-row {
          display: flex;
          align-items: baseline;
          gap: 8px;
          flex-wrap: wrap;
        }

        .trip-command-center h3 {
          margin: 0;
          color: var(--ec-ink);
          font-family: "Iowan Old Style", Georgia, "Times New Roman", serif;
          font-size: clamp(1.42rem, 1.35vw, 1.68rem);
          line-height: 1.05;
          letter-spacing: -0.055em;
          text-wrap: pretty;
        }

        .trip-command-center__header p,
        .trip-command-center__ledger p,
        .trip-command-center__focus p {
          margin: 0;
          color: var(--ec-slate);
          font-size: 11px;
          line-height: 1.58;
          text-wrap: pretty;
        }

        .trip-command-center__header p {
          display: -webkit-box;
          overflow: hidden;
          -webkit-box-orient: vertical;
          -webkit-line-clamp: 2;
        }

        .trip-command-center__status {
          width: fit-content;
          padding: 6px 10px;
          border-radius: 999px;
          font-size: 11px;
          font-weight: 900;
        }

        .trip-command-center__status--stable {
          color: #3f6f45;
          background: rgba(231, 236, 232, 0.96);
        }

        .trip-command-center__status--attention {
          color: var(--ec-clay);
          background: rgba(239, 229, 214, 0.96);
        }

        .trip-command-center__signals,
        .trip-command-center__route-facts {
          display: grid;
          grid-template-columns: repeat(3, minmax(0, 1fr));
          gap: 8px;
        }

        .trip-command-center__route-facts {
          display: block;
          overflow: hidden;
          margin: 0;
          padding: 9px 11px;
          border-radius: 16px;
          border: 1px solid var(--ec-line-soft);
          background: rgba(255,253,249,0.64);
          color: var(--ec-slate);
          font-size: 11px;
          font-weight: 800;
          line-height: 1.45;
          text-overflow: ellipsis;
        }

        .trip-command-center__metric {
          display: grid;
          gap: 4px;
          min-width: 0;
          padding: 9px 10px;
          border-radius: 16px;
          border: 1px solid var(--ec-line-soft);
          background: rgba(255, 253, 249, 0.76);
        }

        .trip-command-center__metric span,
        .trip-command-center__ledger span,
        .trip-command-center__focus span {
          color: var(--ec-slate);
          font-size: 10px;
          font-weight: 900;
          letter-spacing: 0.12em;
          text-transform: uppercase;
        }

        .trip-command-center__metric strong {
          overflow: hidden;
          color: var(--ec-ink);
          font-size: 16px;
          line-height: 1.08;
          text-overflow: ellipsis;
          white-space: nowrap;
        }

        .trip-command-center__metric--moss {
          background: rgba(231, 236, 232, 0.78);
        }

        .trip-command-center__metric--ochre {
          background: rgba(239, 229, 214, 0.82);
        }

        .trip-command-center__metric--ink {
          background: rgba(23, 27, 34, 0.92);
        }

        .trip-command-center__metric--ink span,
        .trip-command-center__metric--ink strong {
          color: #fffdf9;
        }

        .trip-command-center__ledger {
          display: grid;
          grid-template-columns: 1fr;
          gap: 8px;
          padding: 8px;
          border-radius: 18px;
          background: rgba(255, 253, 249, 0.52);
          border: 1px solid var(--ec-line-soft);
        }

        .trip-command-center__ledger summary {
          cursor: pointer;
          list-style: none;
          color: var(--ec-slate);
          font-size: 11px;
          font-weight: 900;
          letter-spacing: 0.12em;
          text-transform: uppercase;
        }

        .trip-command-center__ledger summary::-webkit-details-marker {
          display: none;
        }

        .trip-command-center__ledger div {
          display: grid;
          gap: 4px;
          padding-left: 12px;
          border-left: 2px solid var(--ec-ochre);
        }

        .trip-command-center__ledger div + div {
          border-left-color: var(--ec-moss);
        }

        .trip-command-center__ledger strong,
        .trip-command-center__focus strong {
          color: var(--ec-ink-soft);
          font-size: 15px;
          line-height: 1.22;
        }

        .trip-command-center__focus {
          display: grid;
          gap: 5px;
          padding: 10px 11px;
          border-radius: 16px;
          background:
            linear-gradient(135deg, rgba(239, 229, 214, 0.76), rgba(255, 253, 249, 0.74));
          border: 1px solid rgba(177, 138, 88, 0.16);
        }

        .trip-command-center__focus--quiet {
          background:
            linear-gradient(135deg, rgba(231, 236, 232, 0.7), rgba(255, 253, 249, 0.74));
          border-color: rgba(102, 113, 95, 0.16);
        }

        .trip-command-center__actions {
          display: grid;
          grid-template-columns: 1fr;
          gap: 9px;
        }

        .trip-command-center__action {
          display: grid;
          grid-template-columns: minmax(0, 1fr);
          align-items: center;
          gap: 3px;
          min-height: 46px;
          width: 100%;
          padding: 11px 12px;
          border-radius: 17px;
          border: 1px solid var(--ec-line);
          background: rgba(255, 253, 249, 0.88);
          color: var(--ec-ink-soft);
          text-align: left;
          cursor: pointer;
        }

        .trip-command-center__action:hover {
          transform: translateY(-1px);
          box-shadow: var(--ec-shadow-1);
        }

        .trip-command-center__action:focus-visible {
          outline: none;
          box-shadow: var(--ec-focus-ring);
        }

        .trip-command-center__action strong {
          font-size: 14px;
        }

        .trip-command-center__action span {
          display: block;
          color: var(--ec-slate);
          font-size: 11.5px;
          font-weight: 800;
          line-height: 1.35;
        }

        .trip-command-center__action--primary {
          border-color: transparent;
          background: var(--ec-night);
          color: #ffffff;
        }

        .trip-command-center__action--primary span {
          color: rgba(255, 253, 249, 0.72);
        }

        @media (max-width: 1180px) {
          .trip-command-center__signals {
            grid-template-columns: repeat(3, minmax(0, 1fr));
          }
        }

        @media (max-width: 640px) {
          .trip-command-center {
            padding: 18px 16px 16px;
            border-radius: 28px;
          }

          .trip-command-center__header {
            padding-right: 0;
          }

          .trip-command-center__mapline {
            display: none;
          }

          .trip-command-center__signals {
            grid-template-columns: repeat(3, minmax(0, 1fr));
          }
        }
      `}</style>
    </section>
  );
}

function MetricTile({ signal }: { signal: TripCommandCenterSignal }) {
  return (
    <div className={`trip-command-center__metric trip-command-center__metric--${signal.tone}`}>
      <span>{signal.label}</span>
      <strong>{signal.value}</strong>
    </div>
  );
}

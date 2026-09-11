"use client";

import { ReactNode } from "react";

export type RouteWorkspaceSheetKey = "completion" | "adjust" | "share" | "more";

type RouteWorkspaceShellProps = {
  city: string;
  tripDays: number;
  statusLabel: string;
  statusTone?: "stable" | "attention";
  subtitle: string;
  completionAction: {
    headerLabel: string;
    label: string;
    hint: string;
  };
  editing: boolean;
  onToggleEditing: () => void;
  children: ReactNode;
  activeSheet: RouteWorkspaceSheetKey | null;
  onSheetChange: (sheet: RouteWorkspaceSheetKey | null) => void;
  sheetTitle?: string;
  sheetDescription?: string;
  sheetContent?: ReactNode;
  headerUtility?: ReactNode;
};

const SECONDARY_ACTIONS: Array<{
  key: RouteWorkspaceSheetKey;
  label: string;
  hint: string;
}> = [
  { key: "adjust", label: "改线", hint: "一句话" },
  { key: "share", label: "导出", hint: "分享" },
  { key: "more", label: "依据", hint: "边界" },
];

export function RouteWorkspaceShell({
  city,
  tripDays,
  statusLabel,
  statusTone = "stable",
  subtitle,
  completionAction,
  editing,
  onToggleEditing,
  children,
  activeSheet,
  onSheetChange,
  sheetTitle,
  sheetDescription,
  sheetContent,
  headerUtility,
}: RouteWorkspaceShellProps) {
  return (
    <section className="route-workspace-shell">
      <div className="route-workspace-shell__chrome" />
      <div className="route-workspace-shell__spine" aria-hidden="true" />
      <header className="route-workspace-shell__header">
        <div className="route-workspace-shell__headline">
          <div className="route-workspace-shell__eyebrow">
            <span>{city}</span>
            <span>{tripDays} 天</span>
          </div>
          <div className="route-workspace-shell__title-row">
            <h2>{editing ? "路线编辑台" : "路线工作台"}</h2>
            <span
              className={`route-workspace-shell__status route-workspace-shell__status--${statusTone}`}
            >
              {statusLabel}
            </span>
          </div>
          <p>{subtitle}</p>
        </div>
        <div className="route-workspace-shell__header-actions">
          <button
            type="button"
            aria-pressed={activeSheet === "completion"}
            onClick={() => onSheetChange(activeSheet === "completion" ? null : "completion")}
            className={`ec-interactive-pill route-workspace-shell__repair-action ${
              activeSheet === "completion" ? "is-active" : ""
            }`}
          >
            {completionAction.headerLabel}
          </button>
          {SECONDARY_ACTIONS.map((action) => {
            const active = activeSheet === action.key;
            return (
              <button
                key={`desktop-${action.key}`}
                type="button"
                aria-pressed={active}
                onClick={() => onSheetChange(active ? null : action.key)}
                className={`ec-interactive-pill ${
                  active ? "is-secondary-active" : "is-secondary"
                }`}
              >
                <strong>{action.label}</strong>
                <span>{action.hint}</span>
              </button>
            );
          })}
          <button className="ec-interactive-pill" type="button" onClick={onToggleEditing}>
            {editing ? "保存路线" : "编辑路线"}
          </button>
          {headerUtility ? (
            <div className="route-workspace-shell__header-utility">{headerUtility}</div>
          ) : null}
        </div>
      </header>

      <div className="route-workspace-shell__body">{children}</div>

      <nav className="route-workspace-shell__dock" aria-label="路线操作">
        {[{ key: "completion" as const, label: completionAction.label, hint: completionAction.hint }, ...SECONDARY_ACTIONS].map((action) => {
          const active = activeSheet === action.key;
          return (
            <button
              key={action.key}
              type="button"
              aria-pressed={active}
              onClick={() => onSheetChange(active ? null : action.key)}
              className={`ec-interactive-pill ${active ? "is-active" : ""}`}
            >
              <strong>{action.label}</strong>
              <span>{action.hint}</span>
            </button>
          );
        })}
      </nav>

      {activeSheet && sheetContent ? (
        <div
          className="route-workspace-shell__sheet-overlay"
          role="presentation"
          onClick={() => onSheetChange(null)}
        >
          <section
            className="route-workspace-shell__sheet"
            role="dialog"
            aria-modal="true"
            aria-label={sheetTitle}
            onClick={(event) => event.stopPropagation()}
          >
            <div className="route-workspace-shell__sheet-handle" />
            <div className="route-workspace-shell__sheet-header">
              <div>
                <h3>{sheetTitle}</h3>
                {sheetDescription ? <p>{sheetDescription}</p> : null}
              </div>
              <button
                className="ec-interactive-pill"
                type="button"
                onClick={() => onSheetChange(null)}
              >
                关闭
              </button>
            </div>
            <div className="route-workspace-shell__sheet-content">{sheetContent}</div>
          </section>
        </div>
      ) : null}

      <style>{`
        .route-workspace-shell {
          position: relative;
          overflow: hidden;
          display: grid;
          gap: 18px;
          min-height: 0;
          padding: clamp(20px, 2vw, 30px);
          border-radius: 42px;
          background:
            radial-gradient(circle at top left, rgba(255,253,249,1), rgba(255,253,249,0.76) 32%, transparent 58%),
            radial-gradient(circle at 92% 8%, rgba(102,113,95,0.12), transparent 28%),
            linear-gradient(135deg, rgba(255,253,249,0.99) 0%, rgba(247,244,238,0.97) 100%);
          border: 1px solid var(--ec-line);
          box-shadow: var(--ec-shadow-3);
        }

        .route-workspace-shell__chrome {
          position: absolute;
          inset: 0;
          opacity: 1;
          pointer-events: none;
          background:
            radial-gradient(circle at 82% 18%, rgba(102, 113, 95, 0.14), transparent 28%),
            radial-gradient(circle at 8% 90%, rgba(177, 138, 88, 0.12), transparent 24%),
            linear-gradient(90deg, rgba(21,21,21,0.024) 1px, transparent 1px),
            linear-gradient(180deg, rgba(21,21,21,0.024) 1px, transparent 1px);
          background-size: auto, auto, 34px 34px, 34px 34px;
        }

        .route-workspace-shell__spine {
          position: absolute;
          top: 0;
          bottom: 0;
          left: 0;
          width: 12px;
          background:
            linear-gradient(180deg, rgba(37,99,235,1) 0%, rgba(59,130,246,0.94) 42%, rgba(147,197,253,0.84) 100%);
          box-shadow: 8px 0 34px rgba(37,99,235,0.14);
        }

        .route-workspace-shell__header,
        .route-workspace-shell__body,
        .route-workspace-shell__dock {
          position: relative;
          z-index: 1;
        }

        .route-workspace-shell__header {
          display: flex;
          justify-content: space-between;
          align-items: start;
          gap: 16px;
          padding-bottom: 14px;
          border-bottom: 1px solid var(--ec-line);
        }

        .route-workspace-shell__headline {
          display: grid;
          gap: 6px;
        }

        .route-workspace-shell__eyebrow {
          display: flex;
          gap: 8px;
          color: var(--ec-slate);
          font-size: 12px;
          font-weight: 800;
          letter-spacing: 0.08em;
          text-transform: uppercase;
        }

        .route-workspace-shell__eyebrow span {
          padding: 5px 10px;
          border-radius: 999px;
          background: rgba(255,253,249,0.78);
          border: 1px solid var(--ec-line-soft);
        }

        .route-workspace-shell__title-row {
          display: flex;
          align-items: center;
          gap: 10px;
          flex-wrap: wrap;
        }

        .route-workspace-shell__title-row h2 {
          margin: 0;
          color: var(--ec-ink);
          font-family: "Iowan Old Style", Georgia, "Times New Roman", serif;
          font-size: clamp(1.9rem, 2.7vw, 2.42rem);
          line-height: 0.96;
          letter-spacing: -0.045em;
        }

        .route-workspace-shell__status {
          padding: 6px 10px;
          border-radius: 999px;
          font-size: 12px;
          font-weight: 900;
        }

        .route-workspace-shell__status--stable {
          color: #386149;
          background: rgba(231,236,232,0.96);
        }

        .route-workspace-shell__status--attention {
          color: #8b673e;
          background: rgba(239,229,214,0.96);
        }

        .route-workspace-shell__headline p {
          margin: 0;
          max-width: 620px;
          color: var(--ec-slate);
          font-size: 14px;
          line-height: 1.55;
        }

        .route-workspace-shell__header button {
          border: 1px solid transparent;
          border-radius: 999px;
          padding: 11px 16px;
          background: var(--ec-night);
          color: #ffffff;
          font-weight: 900;
          cursor: pointer;
          white-space: nowrap;
          box-shadow: 0 14px 28px rgba(21, 21, 21, 0.16);
        }

        .route-workspace-shell__header button:hover {
          box-shadow: 0 18px 36px rgba(21, 21, 21, 0.2);
        }

        .route-workspace-shell__repair-action {
          border-color: transparent !important;
          background: #2563eb !important;
          color: #ffffff !important;
          box-shadow: 0 16px 30px rgba(37,99,235,0.22) !important;
        }

        .route-workspace-shell__repair-action.is-active {
          background: var(--ec-night) !important;
          box-shadow: 0 16px 30px rgba(21,21,21,0.18) !important;
        }

        .route-workspace-shell__header-actions {
          display: flex;
          gap: 8px;
          align-items: center;
          flex-wrap: wrap;
          justify-content: flex-end;
          max-width: 520px;
        }

        .route-workspace-shell__header-utility {
          display: inline-flex;
        }

        .route-workspace-shell__header-utility button {
          border: 1px solid var(--ec-line) !important;
          background: rgba(255,253,249,0.9) !important;
          color: var(--ec-ink-soft) !important;
          box-shadow: none !important;
        }

        .route-workspace-shell__header-actions .is-secondary,
        .route-workspace-shell__header-actions .is-secondary-active {
          display: none;
          align-items: center;
          gap: 5px;
          border: 1px solid var(--ec-line);
          background: rgba(255,253,249,0.9);
          color: var(--ec-ink-soft);
          box-shadow: none;
          padding: 10px 13px;
        }

        .route-workspace-shell__header-actions .is-secondary-active {
          border-color: rgba(37,99,235,0.2);
          background: rgba(37,99,235,0.1);
          color: #1f4fb8;
        }

        .route-workspace-shell__header-actions .is-secondary span,
        .route-workspace-shell__header-actions .is-secondary-active span {
          color: var(--ec-slate);
          font-size: 10px;
          font-weight: 900;
          letter-spacing: 0.08em;
          text-transform: uppercase;
        }

        .route-workspace-shell__body {
          min-width: 0;
        }

        .route-workspace-shell__dock {
          position: sticky;
          bottom: 12px;
          display: grid;
          grid-template-columns: repeat(4, minmax(0, 1fr));
          gap: 8px;
          padding: 9px;
          border-radius: 26px;
          background:
            radial-gradient(circle at top left, rgba(239,229,214,0.32), transparent 34%),
            rgba(255,253,249,0.96);
          border: 1px solid var(--ec-line);
          box-shadow: 0 18px 40px rgba(21, 21, 21, 0.12);
          backdrop-filter: blur(16px);
        }

        .route-workspace-shell__dock button {
          display: grid;
          gap: 2px;
          min-width: 0;
          padding: 11px 8px;
          border: none;
          border-radius: 18px;
          color: var(--ec-slate);
          background: transparent;
          cursor: pointer;
        }

        .route-workspace-shell__dock button.is-active {
          color: #ffffff;
          background: var(--ec-night);
          box-shadow: 0 12px 24px rgba(21, 21, 21, 0.16);
        }

        .route-workspace-shell__dock strong {
          font-size: 14px;
        }

        .route-workspace-shell__dock span {
          overflow: hidden;
          text-overflow: ellipsis;
          white-space: nowrap;
          font-size: 11px;
        }

        .route-workspace-shell__sheet-overlay {
          position: fixed;
          z-index: 60;
          inset: 0;
          display: grid;
          align-items: end;
          justify-items: center;
          background: rgba(23, 27, 34, 0.34);
          padding: 16px;
        }

        .route-workspace-shell__sheet {
          width: min(900px, 100%);
          max-height: min(82vh, 860px);
          display: grid;
          grid-template-rows: auto auto minmax(0, 1fr);
          gap: 14px;
          padding: 14px;
          border-radius: 32px 32px 26px 26px;
          background:
            radial-gradient(circle at top right, rgba(102,113,95,0.08), transparent 28%),
            var(--ec-paper-strong);
          border: 1px solid var(--ec-line);
          box-shadow: 0 24px 70px rgba(21, 21, 21, 0.22);
        }

        .route-workspace-shell__sheet-handle {
          justify-self: center;
          width: 56px;
          height: 5px;
          border-radius: 999px;
          background: linear-gradient(90deg, rgba(177,138,88,0.46), rgba(102,113,95,0.46));
        }

        .route-workspace-shell__sheet-header {
          display: flex;
          justify-content: space-between;
          gap: 14px;
          align-items: start;
        }

        .route-workspace-shell__sheet-header h3 {
          margin: 0;
          color: var(--ec-ink);
          font-family: "Iowan Old Style", Georgia, "Times New Roman", serif;
          font-size: 28px;
          line-height: 1;
          letter-spacing: -0.03em;
        }

        .route-workspace-shell__sheet-header p {
          margin: 5px 0 0;
          color: var(--ec-slate);
          line-height: 1.5;
          font-size: 14px;
        }

        .route-workspace-shell__sheet-header button {
          border: none;
          border-radius: 999px;
          padding: 9px 12px;
          background: rgba(21, 21, 21, 0.08);
          color: var(--ec-ink-soft);
          font-weight: 800;
          cursor: pointer;
        }

        .route-workspace-shell__sheet-header button:hover {
          background: rgba(21, 21, 21, 0.12);
        }

        .route-workspace-shell__sheet-content {
          min-height: 0;
          overflow: auto;
          display: grid;
          gap: 16px;
          padding-right: 2px;
        }

        @media (max-width: 720px) {
          .route-workspace-shell {
            min-height: 0;
            padding: 14px;
            border-radius: 28px;
          }

          .route-workspace-shell__header {
            align-items: stretch;
            flex-direction: column;
          }

          .route-workspace-shell__header button {
            width: fit-content;
          }

          .route-workspace-shell__dock {
            bottom: 8px;
          }
        }

        @media (min-width: 820px) {
          .route-workspace-shell {
            padding: clamp(18px, 1.6vw, 24px);
          }

          .route-workspace-shell__header-actions .is-secondary,
          .route-workspace-shell__header-actions .is-secondary-active {
            display: inline-flex;
          }

          .route-workspace-shell__header-actions .is-secondary:nth-of-type(4),
          .route-workspace-shell__header-actions .is-secondary-active:nth-of-type(4) {
            display: none;
          }

          .route-workspace-shell__dock {
            display: none;
          }
        }
      `}</style>
    </section>
  );
}

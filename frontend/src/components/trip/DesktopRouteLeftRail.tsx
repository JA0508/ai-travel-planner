"use client";

import { ReactNode } from "react";

export function DesktopRouteLeftRail({
  commandCenter,
  completion,
  brief,
}: {
  commandCenter?: ReactNode;
  completion: ReactNode;
  brief: ReactNode;
}) {
  return (
    <div className="desktop-route-left-rail">
      {commandCenter ? (
        <section className="desktop-route-left-rail__command">
          {commandCenter}
        </section>
      ) : null}

      <section className="desktop-route-left-rail__section">
        <div className="desktop-route-left-rail__heading">
          <p>Completion Intelligence</p>
          <h3>优先修哪里</h3>
          <span>只保留最能提升可执行性的建议，证据按需展开。</span>
        </div>
        {completion}
      </section>

      <details className="desktop-route-left-rail__brief">
        <summary>
          <span>已识别边界</span>
          <strong>输入 / 偏好 / 当前计划</strong>
        </summary>
        <div className="desktop-route-left-rail__brief-body">{brief}</div>
      </details>

      <style>{`
        .desktop-route-left-rail {
          display: grid;
          gap: 14px;
        }

        .desktop-route-left-rail__command {
          min-width: 0;
        }

        .desktop-route-left-rail__section {
          position: relative;
          overflow: hidden;
          display: grid;
          gap: 12px;
          padding: 18px 15px 16px 19px;
          border-radius: 22px;
          background:
            rgba(252,250,246,0.94);
          border: 1px solid var(--ec-line);
          box-shadow: var(--ec-shadow-1);
        }

        .desktop-route-left-rail__section::before {
          content: "";
          position: absolute;
          top: 0;
          bottom: 0;
          left: 0;
          width: 5px;
          background: #2563eb;
        }

        .desktop-route-left-rail__heading {
          display: grid;
          gap: 5px;
        }

        .desktop-route-left-rail__heading p {
          margin: 0;
          color: #2563eb;
          font-size: 11px;
          font-weight: 800;
          letter-spacing: 0.08em;
          text-transform: uppercase;
        }

        .desktop-route-left-rail__heading h3 {
          margin: 0;
          color: var(--ec-ink);
          font-family: "Iowan Old Style", Georgia, "Times New Roman", serif;
          font-size: 23px;
          line-height: 1;
          letter-spacing: -0.025em;
        }

        .desktop-route-left-rail__heading span {
          color: var(--ec-slate);
          font-size: 12px;
          line-height: 1.5;
        }

        .desktop-route-left-rail__brief {
          overflow: hidden;
          border-radius: 18px;
          background: rgba(255, 253, 249, 0.72);
          border: 1px solid var(--ec-line-soft);
          box-shadow: 0 10px 26px rgba(21, 21, 21, 0.035);
        }

        .desktop-route-left-rail__brief summary {
          cursor: pointer;
          display: grid;
          gap: 3px;
          padding: 13px 15px;
          list-style: none;
        }

        .desktop-route-left-rail__brief summary::-webkit-details-marker {
          display: none;
        }

        .desktop-route-left-rail__brief summary span {
          color: var(--ec-slate);
          font-size: 10px;
          font-weight: 900;
          letter-spacing: 0.12em;
          text-transform: uppercase;
        }

        .desktop-route-left-rail__brief summary strong {
          color: var(--ec-ink-soft);
          font-size: 13px;
          line-height: 1.25;
        }

        .desktop-route-left-rail__brief-body {
          display: grid;
          gap: 9px;
          padding: 0 13px 13px;
        }
      `}</style>
    </div>
  );
}

"use client";

import type { ReplanMutationPlan } from "./replanTypes";

export function ReplanConfirmationDialog({
  plan,
  executing,
  onCancel,
  onConfirm,
}: {
  plan: ReplanMutationPlan | null;
  executing: boolean;
  onCancel: () => void;
  onConfirm: () => void;
}) {
  if (!plan) {
    return null;
  }

  return (
    <div className="replan-confirmation-dialog" role="dialog" aria-modal="true">
      <div className="replan-confirmation-dialog__panel">
        <span>Confirm Replan</span>
        <h3>{plan.title}</h3>
        <p>{plan.summary}</p>
        <div className="replan-confirmation-dialog__actions">
          <button type="button" onClick={onCancel} disabled={executing}>
            返回检查
          </button>
          <button type="button" onClick={onConfirm} disabled={executing || !plan.executable}>
            {executing ? "执行中..." : "确认执行"}
          </button>
        </div>
      </div>
      <style>{`
        .replan-confirmation-dialog {
          position: fixed;
          inset: 0;
          z-index: 80;
          display: grid;
          place-items: center;
          padding: 18px;
          background: rgba(22,28,24,0.28);
        }
        .replan-confirmation-dialog__panel {
          display: grid;
          gap: 10px;
          width: min(420px, 100%);
          padding: 18px;
          border-radius: 20px;
          border: 1px solid var(--ec-line);
          background: rgba(255,253,249,0.98);
          box-shadow: var(--ec-shadow-2);
        }
        .replan-confirmation-dialog span {
          color: var(--ec-slate);
          font-size: 10px;
          font-weight: 950;
          letter-spacing: 0.14em;
          text-transform: uppercase;
        }
        .replan-confirmation-dialog h3 {
          margin: 0;
          color: var(--ec-ink);
          font-family: "Iowan Old Style", Georgia, "Times New Roman", serif;
          font-size: 24px;
          line-height: 1.05;
          letter-spacing: 0;
        }
        .replan-confirmation-dialog p {
          margin: 0;
          color: var(--ec-slate);
          font-size: 13px;
          line-height: 1.55;
        }
        .replan-confirmation-dialog__actions {
          display: flex;
          justify-content: flex-end;
          gap: 10px;
          padding-top: 4px;
        }
        .replan-confirmation-dialog button {
          min-height: 38px;
          padding: 0 14px;
          border-radius: 999px;
          border: 1px solid var(--ec-line);
          background: rgba(255,253,249,0.9);
          color: var(--ec-ink);
          font-weight: 900;
          cursor: pointer;
        }
        .replan-confirmation-dialog button:last-child {
          border-color: rgba(47,111,168,0.42);
          background: var(--ec-route-blue);
          color: #fffdf9;
        }
        .replan-confirmation-dialog button:disabled {
          opacity: 0.58;
          cursor: not-allowed;
        }
      `}</style>
    </div>
  );
}

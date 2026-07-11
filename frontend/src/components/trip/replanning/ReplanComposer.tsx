"use client";

export function ReplanComposer({
  value,
  disabled,
  onChange,
  onInterpret,
}: {
  value: string;
  disabled?: boolean;
  onChange: (value: string) => void;
  onInterpret: () => void;
}) {
  return (
    <section className="replan-composer">
      <label htmlFor="constraint-replan-textarea">调整要求</label>
      <textarea
        id="constraint-replan-textarea"
        rows={4}
        value={value}
        onChange={(event) => onChange(event.target.value)}
        placeholder="例：第二天下午轻一点，晚上想留给吃饭和夜景。"
        disabled={disabled}
      />
      <div className="replan-composer__actions">
        <button type="button" onClick={onInterpret} disabled={disabled || !value.trim()}>
          解析影响
        </button>
        <span>先解释和检查约束，确认后再改行程。</span>
      </div>
      <style>{`
        .replan-composer {
          display: grid;
          gap: 8px;
        }
        .replan-composer label {
          color: var(--ec-slate);
          font-size: 10px;
          font-weight: 950;
          letter-spacing: 0.14em;
          text-transform: uppercase;
        }
        .replan-composer textarea {
          width: 100%;
          resize: vertical;
          min-height: 96px;
          padding: 12px;
          border-radius: 16px;
          border: 1px solid var(--ec-line);
          background: rgba(255,253,249,0.92);
          color: var(--ec-ink);
          font: inherit;
          line-height: 1.5;
        }
        .replan-composer textarea:focus {
          outline: none;
          box-shadow: var(--ec-focus-ring);
        }
        .replan-composer__actions {
          display: flex;
          flex-wrap: wrap;
          gap: 10px;
          align-items: center;
        }
        .replan-composer button {
          min-height: 38px;
          padding: 0 14px;
          border: 1px solid rgba(47,111,168,0.38);
          border-radius: 999px;
          background: rgba(47,111,168,0.11);
          color: var(--ec-route-blue);
          font-weight: 900;
          cursor: pointer;
        }
        .replan-composer button:disabled {
          cursor: not-allowed;
          opacity: 0.58;
        }
        .replan-composer__actions span {
          color: var(--ec-slate);
          font-size: 12px;
          line-height: 1.45;
        }
      `}</style>
    </section>
  );
}

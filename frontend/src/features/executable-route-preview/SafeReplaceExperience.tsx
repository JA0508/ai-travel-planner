"use client";

import React from "react";
import { formatDistance, formatMinutes } from "./routePreviewModel";
import {
  formatSafeReplaceRouteDelta,
  type SafeReplaceCandidate,
  type SafeReplacePreviewModel,
  type SafeReplaceRouteLeg,
} from "./safeReplaceModel";

export function SafeReplaceCandidates({
  targetName,
  candidates,
  loading,
  errorMessage,
  onSelect,
  onKeep,
}: {
  targetName: string;
  candidates: SafeReplaceCandidate[];
  loading: boolean;
  errorMessage?: string;
  onSelect: (candidate: SafeReplaceCandidate) => void;
  onKeep: () => void;
}) {
  return (
    <section className="safe-replace safe-replace--candidates" aria-label={`替换 ${targetName}`}>
      <header className="safe-replace__header">
        <div>
          <p>ONE STOP / A FEW BETTER FITS</p>
          <h2>换一个更适合你的地点</h2>
        </div>
        <button type="button" onClick={onKeep} aria-label="关闭候选地点">×</button>
      </header>
      <p className="safe-replace__lead">我们只替换这一站，其他已经确认的安排不会随意移动。</p>
      {loading ? (
        <p className="safe-replace__status" aria-live="polite">正在找几个真正适合这一站的地方…</p>
      ) : errorMessage ? (
        <p className="safe-replace__status is-error" role="alert">{errorMessage}</p>
      ) : candidates.length ? (
        <>
          <p className="safe-replace__quality-summary">找到 {candidates.length} 个可以安全换进去的地点</p>
          <div className="safe-replace__candidate-list">
            {candidates.slice(0, 3).map((candidate, index) => (
              <article className="safe-replace-candidate is-safe" key={candidate.verified_place.provider_place_id}>
                <span className="safe-replace-candidate__index">{String(index + 1).padStart(2, "0")}</span>
                <div className="safe-replace-candidate__copy">
                  <p>{candidate.verified_place.category ?? (candidate.type === "restaurant" ? "餐食" : "地点")}</p>
                  <h3>{candidate.name}</h3>
                  <strong>{formatSafeReplaceRouteDelta(candidate.route_impact.delta_duration_s)}</strong>
                  <span>{candidate.reasoning_summary}</span>
                </div>
                <button type="button" onClick={() => onSelect(candidate)}>看看换成这里 <i aria-hidden="true">→</i></button>
              </article>
            ))}
          </div>
        </>
      ) : (
        <div className="safe-replace__empty">
          <strong>附近暂时没有找到一个真正适合换进去的地点。</strong>
          <p>我们不会为了凑一个推荐，把明显绕路或者可能打乱安排的地方放进来。</p>
          <button type="button" onClick={onKeep}>保留原地点</button>
        </div>
      )}
      <SafeReplaceStyles />
    </section>
  );
}

export function SafeReplacePreview({
  targetName,
  candidate,
  model,
  applying,
  onApply,
  onKeep,
  onOtherCandidates,
}: {
  targetName: string;
  candidate: SafeReplaceCandidate;
  model?: SafeReplacePreviewModel;
  applying: boolean;
  onApply: () => void;
  onKeep: () => void;
  onOtherCandidates: () => void;
}) {
  const safe = candidate.route_impact.safe_to_apply && Boolean(model);
  return (
    <section className={`safe-replace safe-replace--preview ${safe ? "is-safe" : "is-unsafe"}`} aria-label="地点替换预览" tabIndex={-1}>
      <header className="safe-replace__header">
        <div>
          <p>LOCAL ROUTE CHANGE / BEFORE &amp; AFTER</p>
          <h2>{safe ? "换成这里以后，这一段会这样走" : "这个地点现在不太适合换进去。"}</h2>
        </div>
        <button type="button" onClick={onKeep} aria-label="关闭替换预览">×</button>
      </header>
      <p className="safe-replace__lead">
        {safe
          ? "我们只重新检查了这一个地点前后的路线。"
          : unsafeExplanation(candidate)}
      </p>

      {safe && model ? (
        <>
          <div className="safe-replace__change-summary">
            <span>这次会改变</span>
            <strong>{model.change.beforeName} <i aria-hidden="true">→</i> {model.change.afterName}</strong>
            <b>{formatSafeReplaceRouteDelta(candidate.route_impact.delta_duration_s)}</b>
          </div>
          <div className="safe-replace__diff">
            <RouteColumn label="换之前" name={model.change.beforeName} inbound={model.before.inbound} outbound={model.before.outbound} />
            <RouteColumn label={`换成${candidate.name}以后`} name={model.change.afterName} inbound={model.after.inbound} outbound={model.after.outbound} />
          </div>
          {model.protectedItems.length ? (
            <section className="safe-replace__protected">
              <p>STAYS AS PLANNED</p>
              <h3>保持不变</h3>
              {model.protectedItems.map((item) => (
                <div key={item.id}><span aria-hidden="true">✓</span><strong>{item.name}</strong><small>{item.reason}</small></div>
              ))}
            </section>
          ) : null}
        </>
      ) : (
        <div className="safe-replace__unsafe-note" role="alert">
          <strong>{targetName} 仍然保留在原处。</strong>
          <span>你的原路线没有被改变。</span>
        </div>
      )}

      <footer className="safe-replace__actions">
        <button type="button" className="is-secondary" onClick={safe ? onKeep : onOtherCandidates}>
          {safe ? "保持原地点" : "看看其他地点"}
        </button>
        <button type="button" className="is-primary" onClick={onApply} disabled={!safe || applying}>
          {applying ? "正在保存…" : "换成这个地点"}
        </button>
      </footer>
      <SafeReplaceStyles />
    </section>
  );
}

function RouteColumn({
  label,
  name,
  inbound,
  outbound,
}: {
  label: string;
  name: string;
  inbound: SafeReplaceRouteLeg | null;
  outbound: SafeReplaceRouteLeg | null;
}) {
  return (
    <article className="safe-replace-route">
      <p>{label}</p>
      <RouteLeg leg={inbound} position="前一段" />
      <div className="safe-replace-route__stop"><span>STOP</span><strong>{name}</strong></div>
      <RouteLeg leg={outbound} position="后一段" />
    </article>
  );
}

function RouteLeg({ leg, position }: { leg: SafeReplaceRouteLeg | null; position: string }) {
  return (
    <div className={`safe-replace-route__leg ${leg ? "is-confirmed" : "is-unconfirmed"}`}>
      <i aria-hidden="true" />
      {leg ? (
        <span><b>{leg.fromName} → {leg.toName}</b><small>{formatMinutes(Math.round(leg.durationSeconds / 60))}{leg.distanceMeters != null ? ` · ${formatDistance(leg.distanceMeters)}` : ""} · 路线已确认</small></span>
      ) : (
        <span><b>{position}路线待确认</b><small>暂时无法确认这段路程</small></span>
      )}
    </div>
  );
}

function unsafeExplanation(candidate: SafeReplaceCandidate): string {
  if (candidate.route_impact.blocking_reason === "fixed_event_at_risk") {
    return "换成这里以后，可能赶不上后面的固定安排。";
  }
  if (candidate.route_impact.blocking_reason === "time_slot_conflict") {
    return "换成这里以后，当前时间槽可能不够。";
  }
  return "这个地点的相邻路程还无法确认。";
}

function SafeReplaceStyles() {
  return <style>{`
    .safe-replace{--replace-ink:#171613;--replace-paper:#faf6f0;--replace-muted:#716a62;--replace-line:rgba(23,22,19,.2);--replace-orange:#e65a28;display:grid;gap:24px;margin:26px 0 42px;border-top:4px solid var(--replace-ink);border-bottom:1px solid var(--replace-ink);background:var(--replace-paper);padding:24px 0 30px;color:var(--replace-ink)}
    .safe-replace__header{display:flex;justify-content:space-between;align-items:start;gap:28px}.safe-replace__header p,.safe-replace__protected>p{margin:0;color:var(--replace-orange);font-size:10px;font-weight:900;letter-spacing:.14em}.safe-replace__header h2{max-width:820px;margin:7px 0 0;font-family:"Arial Narrow","Avenir Next Condensed","Noto Sans SC",sans-serif;font-size:38px;line-height:1}.safe-replace__header>button{display:grid;width:40px;height:40px;flex:0 0 auto;place-items:center;border:1px solid var(--replace-ink);border-radius:50%;background:transparent;color:var(--replace-ink);font-size:24px;cursor:pointer}.safe-replace__lead{max-width:760px;margin:0;color:var(--replace-muted);font-family:"Iowan Old Style","Songti SC",Georgia,serif;font-size:16px;line-height:1.7}.safe-replace__status{margin:0;border-left:3px solid var(--replace-orange);padding:18px 20px;background:#f2ece3;color:var(--replace-muted);line-height:1.65}.safe-replace__status.is-error{color:#7f3026}
    .safe-replace__quality-summary{margin:0;color:var(--replace-ink);font-size:13px;font-weight:900}.safe-replace__candidate-list{display:grid;border-top:1px solid var(--replace-line)}.safe-replace-candidate{display:grid;grid-template-columns:54px minmax(0,1fr) auto;gap:22px;align-items:center;border-bottom:1px solid var(--replace-line);padding:22px 4px}.safe-replace-candidate__index{align-self:start;color:var(--replace-orange);font-size:12px;font-weight:900}.safe-replace-candidate__copy{display:grid;gap:6px}.safe-replace-candidate__copy p{margin:0;color:var(--replace-muted);font-size:9px;font-weight:900;letter-spacing:.12em}.safe-replace-candidate__copy h3{margin:0;font-family:"Arial Narrow","Avenir Next Condensed","Noto Sans SC",sans-serif;font-size:30px;line-height:1}.safe-replace-candidate__copy strong{font-size:13px}.safe-replace-candidate__copy>span{max-width:620px;color:var(--replace-muted);font-family:"Iowan Old Style","Songti SC",Georgia,serif;font-size:14px;line-height:1.55}.safe-replace-candidate>button{border:0;border-bottom:1px solid currentColor;background:transparent;padding:9px 0;color:var(--replace-ink);font:inherit;font-size:13px;font-weight:900;cursor:pointer}.safe-replace-candidate>button i{margin-left:7px;color:var(--replace-orange);font-style:normal}.safe-replace__empty{display:grid;gap:10px;border-left:3px solid var(--replace-orange);padding:20px;background:#f2ece3}.safe-replace__empty strong{font-family:"Iowan Old Style","Songti SC",Georgia,serif;font-size:19px;line-height:1.45}.safe-replace__empty p{max-width:720px;margin:0;color:var(--replace-muted);line-height:1.65}.safe-replace__empty button{justify-self:start;border:0;border-bottom:1px solid currentColor;background:transparent;padding:8px 0;color:var(--replace-ink);font:inherit;font-weight:900;cursor:pointer}
    .safe-replace__change-summary{display:grid;grid-template-columns:150px minmax(0,1fr) auto;gap:22px;align-items:center;border-top:1px solid var(--replace-line);border-bottom:1px solid var(--replace-line);padding:18px 0}.safe-replace__change-summary>span{color:var(--replace-muted);font-size:10px;font-weight:900;letter-spacing:.1em}.safe-replace__change-summary>strong{font-family:"Iowan Old Style","Songti SC",Georgia,serif;font-size:21px}.safe-replace__change-summary i{color:var(--replace-orange);font-style:normal}.safe-replace__change-summary>b{color:var(--replace-orange);font-size:13px}.safe-replace__diff{display:grid;grid-template-columns:1fr 1fr;border-top:1px solid var(--replace-ink);border-bottom:1px solid var(--replace-ink)}.safe-replace-route{display:grid;align-content:start;min-width:0;padding:22px 28px}.safe-replace-route+ .safe-replace-route{border-left:1px solid var(--replace-ink);background:#f1ebe2}.safe-replace-route>p{margin:0 0 18px;color:var(--replace-orange);font-size:10px;font-weight:900;letter-spacing:.12em}.safe-replace-route__stop{display:grid;gap:5px;border-top:2px solid var(--replace-ink);border-bottom:2px solid var(--replace-ink);padding:17px 0}.safe-replace-route__stop span{color:var(--replace-muted);font-size:9px;font-weight:900;letter-spacing:.12em}.safe-replace-route__stop strong{font-family:"Arial Narrow","Avenir Next Condensed","Noto Sans SC",sans-serif;font-size:28px}.safe-replace-route__leg{display:grid;grid-template-columns:22px minmax(0,1fr);gap:10px;min-height:76px;align-items:center;padding:9px 0}.safe-replace-route__leg>i{justify-self:center;width:2px;height:58px;background:var(--replace-orange)}.safe-replace-route__leg>span{display:grid;gap:3px;min-width:0}.safe-replace-route__leg b{font-size:12px}.safe-replace-route__leg small{color:var(--replace-muted);font-size:10px;line-height:1.45}.safe-replace-route__leg.is-unconfirmed>i{background:repeating-linear-gradient(to bottom,var(--replace-orange) 0 4px,transparent 4px 8px)}
    .safe-replace__protected{display:grid;grid-template-columns:160px minmax(0,1fr);gap:0 26px;border-top:3px solid var(--replace-ink);padding-top:17px}.safe-replace__protected h3{grid-column:1;margin:6px 0 14px;font-family:"Iowan Old Style","Songti SC",Georgia,serif;font-size:26px}.safe-replace__protected>div{grid-column:2;display:grid;grid-template-columns:24px minmax(120px,.5fr) minmax(0,1fr);gap:12px;border-bottom:1px solid var(--replace-line);padding:9px 0}.safe-replace__protected>div>span{color:var(--replace-orange);font-weight:900}.safe-replace__protected small{color:var(--replace-muted)}.safe-replace__unsafe-note{display:grid;gap:8px;border-left:4px solid var(--replace-orange);padding:22px;background:#f3e9df}.safe-replace__unsafe-note strong{font-family:"Iowan Old Style","Songti SC",Georgia,serif;font-size:20px}.safe-replace__unsafe-note span{color:var(--replace-muted)}.safe-replace__actions{display:flex;justify-content:flex-end;gap:12px}.safe-replace__actions button{min-height:48px;border:1px solid var(--replace-ink);border-radius:3px;padding:0 20px;font:inherit;font-weight:900;cursor:pointer}.safe-replace__actions .is-secondary{background:transparent;color:var(--replace-ink)}.safe-replace__actions .is-primary{background:var(--replace-ink);color:#fff}.safe-replace__actions button:disabled{opacity:.45;cursor:not-allowed}.safe-replace button:focus-visible{outline:3px solid rgba(230,90,40,.42);outline-offset:3px}
    @media(max-width:680px){.safe-replace{margin:20px -18px 34px;padding:22px 18px 26px}.safe-replace__header h2{font-size:31px}.safe-replace__lead{font-size:14px}.safe-replace-candidate{grid-template-columns:32px minmax(0,1fr);gap:12px}.safe-replace-candidate>button{grid-column:2;justify-self:start}.safe-replace__change-summary{grid-template-columns:1fr;gap:7px}.safe-replace__diff{grid-template-columns:1fr}.safe-replace-route{padding:20px 4px}.safe-replace-route+ .safe-replace-route{border-top:1px solid var(--replace-ink);border-left:0}.safe-replace__protected{grid-template-columns:1fr}.safe-replace__protected h3,.safe-replace__protected>div{grid-column:1}.safe-replace__protected>div{grid-template-columns:22px minmax(0,1fr)}.safe-replace__protected small{grid-column:2}.safe-replace__actions{display:grid}.safe-replace__actions button{width:100%}}
  `}</style>;
}

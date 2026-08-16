import React, { useEffect, useMemo, useRef } from "react";

import { formatDistance, formatMinutes, type RoutePreviewItinerary } from "./routePreviewModel";
import {
  buildRepairPreviewModel,
  type LocalRepairImpact,
  type RepairRouteItem,
  type RepairRouteSection,
} from "./repairPreviewModel";

type Props = {
  before: RoutePreviewItinerary;
  after: RoutePreviewItinerary;
  targetDay: number;
  impact: LocalRepairImpact;
  applying: boolean;
  onKeep: () => void;
  onApply: () => void;
};

export function RoadbookRepairPreview({
  before,
  after,
  targetDay,
  impact,
  applying,
  onKeep,
  onApply,
}: Props) {
  const rootRef = useRef<HTMLElement>(null);
  const model = useMemo(
    () => buildRepairPreviewModel(before, after, targetDay, impact),
    [after, before, impact, targetDay],
  );
  const actionLabel = repairActionLabel(model.change);

  useEffect(() => {
    const behavior = window.matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth";
    rootRef.current?.scrollIntoView({ behavior, block: "start" });
    rootRef.current?.focus({ preventScroll: true });
  }, []);

  return (
    <section
      ref={rootRef}
      className="repair-proof"
      role="region"
      aria-labelledby="repair-preview-title"
      data-repair-preview="true"
      tabIndex={-1}
    >
      <header className="repair-proof__heading">
        <div>
          <p>ROUTE NOTE / BEFORE &amp; AFTER</p>
          <h2 id="repair-preview-title">我们建议只调整这一段</h2>
        </div>
        <span>固定安排和你明确想去的地点不会被随意移动。</span>
      </header>

      <div className="repair-proof__compare">
        <RepairColumn label="调整前" sections={model.beforeSections} side="before" />
        <span className="repair-proof__arrow" aria-hidden="true">→</span>
        <RepairColumn label="调整后" sections={model.afterSections} side="after" />
      </div>

      <div className="repair-proof__evidence">
        <article className="repair-proof__change">
          <p>这次会改变</p>
          <strong>{actionLabel}</strong>
          <span>{quantitativeSummary(model.quantitativeImpact, targetDay)}</span>
        </article>
        <article className="repair-proof__why">
          <p>为什么这样调？</p>
          <span>{model.reason}</span>
        </article>
        {model.protectedItems.length ? (
          <article className="repair-proof__protected">
            <p>保持不变</p>
            <ul>
              {model.protectedItems.map((item) => (
                <li key={item.id}>
                  <b aria-hidden="true">✓</b>
                  <span>
                    <strong>{item.name}{item.reason.startsWith("已经") ? ` · ${item.time.slice(0, 5)}` : ""}</strong>
                    <small>{item.reason}</small>
                  </span>
                </li>
              ))}
            </ul>
          </article>
        ) : null}
      </div>

      <footer className="repair-proof__actions">
        <button type="button" onClick={onKeep} disabled={applying}>保持原路线</button>
        <button type="button" onClick={onApply} disabled={applying}>
          {applying ? "正在保存调整…" : "应用这次调整"}
          <span aria-hidden="true">→</span>
        </button>
      </footer>
      <RepairPreviewStyles />
    </section>
  );
}

function RepairColumn({
  label,
  sections,
  side,
}: {
  label: string;
  sections: RepairRouteSection[];
  side: "before" | "after";
}) {
  return (
    <article className={`repair-proof__column is-${side}`}>
      <h3>{label}</h3>
      {sections.map((section) => (
        <section key={section.day}>
          <p>DAY {String(section.day).padStart(2, "0")}</p>
          {section.items.length ? (
            <div className="repair-proof__route">
              {section.items.map((item) => <RepairItem key={item.id} item={item} side={side} />)}
            </div>
          ) : <span className="repair-proof__empty">这一天的其他安排不在本次改动中。</span>}
        </section>
      ))}
    </article>
  );
}

function RepairItem({ item, side }: { item: RepairRouteItem; side: "before" | "after" }) {
  return (
    <div className={`repair-proof__route-unit${item.changed ? " is-changed" : ""}`}>
      {item.travelFromName ? (
        <div className="repair-proof__leg">
          <i aria-hidden="true">│</i>
          <span>{item.travelConfirmed && item.travelDurationSeconds != null
            ? `${formatMinutes(Math.round(item.travelDurationSeconds / 60))}${item.travelDistanceMeters != null ? ` · ${formatDistance(item.travelDistanceMeters)}` : ""}`
            : "路线待确认"}</span>
        </div>
      ) : null}
      <div className="repair-proof__stop">
        <time>{item.startTime.slice(0, 5)}</time>
        <span aria-hidden="true" />
        <div>
          <strong>{item.name}</strong>
          {item.changed ? <small>{side === "before" ? "从这里调整" : "调整后的位置"}</small> : item.fixed ? <small>LOCKED · 已经留好的时间</small> : item.mustVisit ? <small>MUST GO · 你明确想去</small> : null}
        </div>
      </div>
    </div>
  );
}

function repairActionLabel(change: ReturnType<typeof buildRepairPreviewModel>["change"]): string {
  if (change.action === "move" && change.toDay) {
    return `把“${change.stopName}”从第 ${change.fromDay} 天挪到第 ${change.toDay} 天`;
  }
  if (change.action === "remove") return `拿掉“${change.stopName}”这个系统补充停留点`;
  if (change.action === "replace") return `替换“${change.stopName}”所在的一段`;
  return `缩短“${change.stopName}”所在的一段`;
}

function quantitativeSummary({
  activityDelta,
  travelMinutesSaved,
}: ReturnType<typeof buildRepairPreviewModel>["quantitativeImpact"], targetDay: number): string {
  const facts = [
    activityDelta ? `第 ${targetDay} 天少 ${activityDelta} 个停留点` : null,
    travelMinutesSaved ? `路上少约 ${formatMinutes(travelMinutesSaved)}` : null,
  ].filter((value): value is string => Boolean(value));
  return facts.length ? facts.join(" · ") : "只展示服务端已经确认的变化，不估算不确定的节省时间。";
}

function RepairPreviewStyles() {
  return <style>{`
    .repair-proof{--repair-paper:#fffaf2;--repair-ink:#171613;--repair-muted:#706a62;--repair-line:rgba(23,22,19,.17);--repair-orange:#e65a28;position:relative;z-index:8;display:grid;gap:26px;margin:-1px 0 44px;border-top:5px solid var(--repair-orange);border-bottom:1px solid var(--repair-ink);background:var(--repair-paper);padding:34px 38px;color:var(--repair-ink)}
    .repair-proof__heading{display:grid;grid-template-columns:minmax(0,1fr) minmax(260px,.55fr);gap:32px;align-items:end}.repair-proof__heading p,.repair-proof__evidence article>p,.repair-proof__column>section>p{margin:0;color:var(--repair-orange);font-size:10px;font-weight:900;letter-spacing:.15em}.repair-proof__heading h2{margin:7px 0 0;font-family:"Iowan Old Style","Songti SC",Georgia,serif;font-size:38px;line-height:1}.repair-proof__heading>span{color:var(--repair-muted);font-family:"Iowan Old Style","Songti SC",Georgia,serif;font-size:15px;line-height:1.65}
    .repair-proof__compare{display:grid;grid-template-columns:minmax(0,1fr) 42px minmax(0,1fr);gap:12px;align-items:start}.repair-proof__arrow{display:grid;place-items:center;padding-top:72px;color:var(--repair-orange);font-size:28px}.repair-proof__column{min-width:0;border-top:1px solid var(--repair-ink);padding-top:14px}.repair-proof__column>h3{margin:0 0 16px;font-family:"Arial Narrow","Avenir Next Condensed","Noto Sans SC",sans-serif;font-size:25px}.repair-proof__column>section{display:grid;gap:10px}.repair-proof__column>section+section{margin-top:18px;border-top:1px dashed var(--repair-line);padding-top:17px}.repair-proof__route{display:grid}.repair-proof__route-unit{position:relative}.repair-proof__leg{display:grid;grid-template-columns:18px minmax(0,1fr);gap:5px;margin-left:74px;padding:9px 0;color:var(--repair-muted);font-size:10px}.repair-proof__leg i{color:var(--repair-orange);font-size:18px;font-style:normal;line-height:.6}.repair-proof__stop{display:grid;grid-template-columns:56px 18px minmax(0,1fr);gap:9px;align-items:start;border-top:1px solid var(--repair-line);padding:13px 8px}.repair-proof__stop>time{padding-top:4px;color:var(--repair-muted);font-size:11px;font-weight:900}.repair-proof__stop>span{width:13px;height:13px;margin-top:3px;border:2px solid var(--repair-paper);border-radius:50%;background:var(--repair-orange);box-shadow:0 0 0 1px var(--repair-orange)}.repair-proof__stop>div{display:grid;gap:3px}.repair-proof__stop strong{font-size:15px}.repair-proof__stop small{color:var(--repair-muted);font-size:10px}.repair-proof__route-unit.is-changed .repair-proof__stop{background:rgba(230,90,40,.1)}.repair-proof__route-unit.is-changed .repair-proof__stop strong{color:#9a3514}.repair-proof__column.is-before .repair-proof__route-unit.is-changed .repair-proof__stop strong{text-decoration:line-through;text-decoration-thickness:1px}.repair-proof__empty{color:var(--repair-muted);font-size:12px}
    .repair-proof__evidence{display:grid;grid-template-columns:.8fr 1fr 1.2fr;border-top:1px solid var(--repair-line);border-bottom:1px solid var(--repair-line)}.repair-proof__evidence article{padding:21px 24px}.repair-proof__evidence article+article{border-left:1px solid var(--repair-line)}.repair-proof__change{display:grid;align-content:start;gap:9px}.repair-proof__change>strong{font-family:"Iowan Old Style","Songti SC",Georgia,serif;font-size:20px;line-height:1.3}.repair-proof__change>span,.repair-proof__why>span{color:var(--repair-muted);font-size:12px;line-height:1.6}.repair-proof__why{display:grid;align-content:start;gap:9px}.repair-proof__protected ul{display:grid;gap:11px;margin:10px 0 0;padding:0;list-style:none}.repair-proof__protected li{display:grid;grid-template-columns:20px minmax(0,1fr);gap:7px}.repair-proof__protected li>b{color:#4f684c}.repair-proof__protected li>span{display:grid;gap:2px}.repair-proof__protected li strong{font-size:13px}.repair-proof__protected li small{color:var(--repair-muted);font-size:11px}.repair-proof__actions{display:flex;justify-content:flex-end;gap:12px}.repair-proof__actions button{min-height:44px;border:1px solid var(--repair-ink);padding:10px 17px;background:transparent;color:var(--repair-ink);font:inherit;font-size:13px;font-weight:900;cursor:pointer}.repair-proof__actions button:last-child{display:flex;align-items:center;gap:20px;background:var(--repair-ink);color:#fff}.repair-proof__actions button:last-child span{color:var(--repair-orange)}.repair-proof__actions button:disabled{opacity:.55;cursor:wait}.repair-proof__actions button:focus-visible{outline:3px solid rgba(230,90,40,.4);outline-offset:3px}
    @media(max-width:760px){.repair-proof{gap:15px;margin:0 -18px 32px;padding:22px 18px 24px}.repair-proof__heading{grid-template-columns:1fr;gap:7px}.repair-proof__heading h2{font-size:29px}.repair-proof__heading>span{font-size:13px}.repair-proof__compare{grid-template-columns:1fr;gap:9px}.repair-proof__arrow{height:20px;padding:0;transform:rotate(90deg);font-size:23px}.repair-proof__column>h3{margin-bottom:8px;font-size:22px}.repair-proof__column>section{gap:4px}.repair-proof__column>section+section{margin-top:8px;padding-top:8px}.repair-proof__leg{margin-left:72px;padding:4px 0}.repair-proof__stop{padding:8px 5px}.repair-proof__stop>div{gap:1px}.repair-proof__stop strong{font-size:14px}.repair-proof__evidence{grid-template-columns:1fr}.repair-proof__evidence article{padding:14px 0}.repair-proof__evidence article+article{border-top:1px solid var(--repair-line);border-left:0}.repair-proof__actions{display:grid;grid-template-columns:1fr 1.25fr;margin:0 -5px;padding:8px;background:var(--repair-paper);border-top:1px solid var(--repair-line)}.repair-proof__actions button{padding:9px 10px}.repair-proof__actions button:last-child{justify-content:center;gap:8px}}
    @media(prefers-reduced-motion:reduce){.repair-proof *{scroll-behavior:auto}}
  `}</style>;
}

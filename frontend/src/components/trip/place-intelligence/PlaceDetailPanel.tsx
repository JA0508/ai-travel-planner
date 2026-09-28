"use client";

import { useEffect, useRef } from "react";
import { PlaceActions } from "./PlaceActions";
import { PlaceCaveats } from "./PlaceCaveats";
import { PlaceDetailHeader } from "./PlaceDetailHeader";
import { PlaceEvidenceCard } from "./PlaceEvidenceCard";
import { PlaceTrustCard } from "./PlaceTrustCard";
import { RouteFitCard } from "./RouteFitCard";
import { VisitContextCard } from "./VisitContextCard";
import type { PlaceDetailViewModel } from "./placeDetailViewModel";

export function PlaceDetailPanel({
  viewModel,
  onBack,
  onRemove,
  onMoveToUnplanned,
  onSelectNext,
  appearance = "default",
}: {
  viewModel: PlaceDetailViewModel;
  onBack: () => void;
  onRemove?: () => void;
  onMoveToUnplanned?: () => void;
  onSelectNext?: (stopId: string) => void;
  appearance?: "default" | "roadbook";
}) {
  const panelRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    if (appearance !== "roadbook") {
      panelRef.current?.focus();
    }
  }, [appearance, viewModel.identity.id]);

  if (appearance === "roadbook") {
    return (
      <article
        ref={panelRef}
        tabIndex={-1}
        className={`roadbook-place ${viewModel.identity.photoUrl ? "has-photo" : "without-photo"}`}
        data-place-detail-panel="true"
        data-roadbook-selected-place={viewModel.identity.id}
        aria-label={`${viewModel.identity.name}地点详情`}
      >
        {viewModel.identity.photoUrl ? (
          <figure className="roadbook-place__photo">
            <img src={viewModel.identity.photoUrl} alt={viewModel.identity.name} />
            <figcaption>FIELD NOTE / PLACE PHOTO</figcaption>
          </figure>
        ) : null}
        <div className="roadbook-place__copy">
          <p className="roadbook-place__eyebrow">
            {viewModel.identity.category ?? "地点"} / DAY {String(viewModel.schedule.dayIndex).padStart(2, "0")}
          </p>
          <h3>{viewModel.identity.name}</h3>
          <p className="roadbook-place__reason">
            {userFacingReason(viewModel)}
          </p>
          <dl>
            <div>
              <dt>留在这里</dt>
              <dd>{formatClock(viewModel.schedule.startTime)}-{formatClock(viewModel.schedule.endTime)}{viewModel.schedule.durationLabel ? ` · ${viewModel.schedule.durationLabel}` : ""}</dd>
            </div>
            <div>
              <dt>路线位置</dt>
              <dd>{viewModel.routeFit.spatialSummary}</dd>
            </div>
            <div>
              <dt>核验状态</dt>
              <dd>{roadbookVerificationStatus(viewModel)}</dd>
            </div>
            {openingHoursSnapshot(viewModel) ? <div><dt>营业时间快照</dt><dd>{openingHoursSnapshot(viewModel)?.detail}</dd></div> : null}
            {viewModel.identity.address ? <div><dt>地址</dt><dd>{viewModel.identity.address}</dd></div> : null}
          </dl>
          {viewModel.caveats.length ? (
            <p className="roadbook-place__note">出发前留意：{viewModel.caveats[0].detail}</p>
          ) : null}
          <div className="roadbook-place__footer">
            <span>NEXT / {viewModel.routeFit.nextStop?.name ?? "当天收口"}</span>
            <button
              type="button"
              onClick={() => viewModel.routeFit.nextStop && onSelectNext
                ? onSelectNext(viewModel.routeFit.nextStop.id)
                : onBack()}
              aria-label={viewModel.routeFit.nextStop ? `查看下一站 ${viewModel.routeFit.nextStop.name}` : "回到当天第一站"}
            >
              {viewModel.routeFit.nextStop ? "→" : "←"}
            </button>
          </div>
        </div>
        <style>{`
          .roadbook-place{display:grid;grid-template-columns:minmax(0,.82fr) minmax(0,1.18fr);min-height:278px;border-top:1px solid var(--roadbook-ink,#171613);border-bottom:1px solid rgba(23,22,19,.18);background:#f8f3eb;color:var(--roadbook-ink,#171613)}
          .roadbook-place:focus{outline:none}.roadbook-place:focus-visible{outline:3px solid rgba(230,90,40,.42);outline-offset:3px}
          .roadbook-place__photo{position:relative;min-height:278px;margin:0;overflow:hidden;background:#ded8ce}.roadbook-place__photo img{position:absolute;inset:0;width:100%;height:100%;object-fit:cover}.roadbook-place__photo figcaption{position:absolute;left:12px;bottom:10px;background:#171613;color:#fff;padding:6px 8px;font-size:9px;font-weight:900;letter-spacing:.12em}
          .roadbook-place__copy{display:grid;align-content:start;gap:14px;padding:25px 28px}.roadbook-place__eyebrow{margin:0;color:#e65a28;font-size:10px;font-weight:900;letter-spacing:.14em}.roadbook-place h3{margin:0;color:#171613;font-family:"Arial Narrow","Avenir Next Condensed","Noto Sans SC",sans-serif;font-size:38px;font-stretch:condensed;line-height:.92}.roadbook-place__reason{margin:0;color:#4f4a44;font-family:"Iowan Old Style","Songti SC",Georgia,serif;font-size:17px;line-height:1.65}
          .roadbook-place.without-photo .roadbook-place__copy{grid-column:1/-1;max-width:720px}
          .roadbook-place dl{display:grid;margin:0}.roadbook-place dl div{display:grid;grid-template-columns:90px minmax(0,1fr);gap:14px;padding:10px 0;border-top:1px solid rgba(23,22,19,.14)}.roadbook-place dt{color:#817970;font-size:10px;font-weight:900;letter-spacing:.09em}.roadbook-place dd{margin:0;color:#26231f;font-size:12px;line-height:1.55}.roadbook-place__note{margin:0;border-left:3px solid #e65a28;padding-left:10px;color:#655a50;font-size:12px;line-height:1.55}
          .roadbook-place__footer{display:flex;justify-content:space-between;align-items:center;gap:16px;margin-top:2px;padding-top:12px;border-top:1px solid rgba(23,22,19,.14);color:#817970;font-size:9px;font-weight:900;letter-spacing:.12em}.roadbook-place__footer button{display:grid;width:38px;height:38px;place-items:center;border:1px solid #171613;border-radius:50%;background:#171613;color:#fff;font-size:18px;cursor:pointer}.roadbook-place__footer button:focus-visible{outline:3px solid rgba(230,90,40,.42);outline-offset:2px}
          @media(max-width:720px){.roadbook-place{grid-template-columns:1fr}.roadbook-place__photo{min-height:210px}.roadbook-place__copy{padding:22px 18px}.roadbook-place h3{font-size:34px}.roadbook-place dl div{grid-template-columns:78px minmax(0,1fr)}}
        `}</style>
      </article>
    );
  }

  return (
    <div
      ref={panelRef}
      tabIndex={-1}
      className="place-detail-panel"
      data-place-detail-panel="true"
      onKeyDown={(event) => {
        if (event.key === "Escape") {
          event.preventDefault();
          onBack();
        }
      }}
    >
      <div className="place-detail-panel__scroll">
        <PlaceDetailHeader viewModel={viewModel} onClose={onBack} />
        <PlaceTrustCard trust={viewModel.trust} />
        <RouteFitCard routeFit={viewModel.routeFit} currentName={viewModel.identity.name} />
        <VisitContextCard visitContext={viewModel.visitContext} />
        <PlaceCaveats caveats={viewModel.caveats} />
        <PlaceEvidenceCard evidence={viewModel.evidence} />
      </div>
      <PlaceActions
        actions={viewModel.actions}
        onBack={onBack}
        onRemove={onRemove}
        onMoveToUnplanned={onMoveToUnplanned}
      />
      <style>{`
        .place-detail-panel {
          min-height: 0;
          height: 100%;
          display: grid;
          grid-template-rows: minmax(0, 1fr) auto;
          gap: 10px;
          padding: 12px;
          border-radius: 22px;
          border: 1px solid var(--ec-line);
          background: linear-gradient(180deg, rgba(255,253,249,0.98), rgba(247,244,238,0.96));
          box-shadow: var(--ec-shadow-1);
        }
        .place-detail-panel:focus {
          outline: none;
        }
        .place-detail-panel:focus-visible {
          box-shadow: var(--ec-focus-ring);
        }
        .place-detail-panel__scroll {
          min-height: 0;
          overflow-y: auto;
          display: grid;
          align-content: start;
          gap: 12px;
          padding-right: 2px;
        }
      `}</style>
    </div>
  );
}

function formatClock(value?: string): string {
  return value ? value.slice(0, 5) : "待确认";
}

function userFacingReason(viewModel: PlaceDetailViewModel): string {
  const reason = viewModel.visitContext.reason;
  return reason && /[\u3400-\u9fff]/.test(reason)
    ? reason
    : viewModel.routeFit.spatialSummary;
}

function roadbookVerificationStatus(viewModel: PlaceDetailViewModel): string {
  const observation = formatObservationTime(viewModel.identity.observedAt);
  const observationPrefix = observation ? `地点详情查询于 ${observation}。` : "";
  const fixedArrangementNotice = viewModel.visitContext.role === "fixed-event"
    ? "这个固定安排会按你的输入保护；系统尚未核验订单、入场资格或预约状态。"
    : "";
  const hasMissingOperationalFact = viewModel.caveats.some((caveat) => caveat.key === "missing-open-time");
  const openingHours = openingHoursSnapshot(viewModel);
  const openingHoursCoverage = openingHoursCoverageEvidence(viewModel);
  if (hasMissingOperationalFact) {
    return `${observationPrefix}地点详情（如营业时间）待验证；当前安排只是时间骨架，不能确认该地点在此时开放。${fixedArrangementNotice}`;
  }
  if (openingHours) {
    const coverageNotice = openingHoursCoverage?.detail
      ?? `这是地点详情查询快照，尚未确认是否覆盖 ${formatClock(viewModel.schedule.startTime)}-${formatClock(viewModel.schedule.endTime)}，也不代表已完成预约。`;
    return `${openingHours.detail}。${coverageNotice}${fixedArrangementNotice}`;
  }
  if (viewModel.trust.verdict === "uncertain-fit") {
    return `${observationPrefix}地点详情或相邻路线仍待验证；当前安排只是时间骨架，不能确认该地点在此时开放。${fixedArrangementNotice}`;
  }
  if (viewModel.trust.verdict === "needs-review") {
    return `${observationPrefix}地点详情可用；相邻路线仍建议复核。${fixedArrangementNotice}`;
  }
  return `${observationPrefix}地点详情与相邻路线已有可用证据。${fixedArrangementNotice}`;
}

function openingHoursSnapshot(viewModel: PlaceDetailViewModel) {
  return viewModel.evidence.find((item) => item.key === "provider-opening-hours");
}

function openingHoursCoverageEvidence(viewModel: PlaceDetailViewModel) {
  return viewModel.evidence.find((item) => item.key === "provider-opening-hours-coverage");
}

function formatObservationTime(observedAt?: string): string | null {
  if (!observedAt || Number.isNaN(Date.parse(observedAt))) {
    return null;
  }

  return new Intl.DateTimeFormat("zh-CN", {
    dateStyle: "medium",
    timeStyle: "short",
    timeZone: "Asia/Shanghai",
  }).format(new Date(observedAt));
}

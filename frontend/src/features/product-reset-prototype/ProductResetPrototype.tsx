"use client";

import { useState } from "react";
import {
  applyFixtureRepair,
  findFixedEvent,
  findTravelLeg,
  type Activity,
  type PrototypeScenario,
  type TripIntentSummary,
  type TripRoute,
} from "./productResetModel";
import { fixtureForScenario, productResetFixtures } from "./productResetFixture";
import styles from "./productResetPrototype.module.css";

type Stage = "input" | "confirm" | "route";
type RepairState = "idle" | "review" | "applied";

const travelModeCopy = {
  walk: "步行",
  metro: "地铁",
  taxi: "打车",
  bus: "公交",
} as const;

export function ProductResetPrototype() {
  const [scenario, setScenario] = useState<PrototypeScenario>("hangzhou");
  const [stage, setStage] = useState<Stage>("input");
  const [repairState, setRepairState] = useState<RepairState>("idle");
  const fixture = fixtureForScenario(scenario);
  const [draftText, setDraftText] = useState(fixture.draft.naturalLanguageRequest);
  const [intent, setIntent] = useState<TripIntentSummary>(fixture.intent);
  const route = repairState === "applied" && fixture.repair
    ? applyFixtureRepair(fixture.route, fixture.repair)
    : fixture.route;

  function selectScenario(nextScenario: PrototypeScenario) {
    const nextFixture = fixtureForScenario(nextScenario);
    setScenario(nextScenario);
    setDraftText(nextFixture.draft.naturalLanguageRequest);
    setIntent(nextFixture.intent);
    setRepairState("idle");
    setStage("input");
  }

  return (
    <main className={styles.page}>
      <header className={styles.topbar}>
        <p>行程草图</p>
        <span>先把这次旅行说清楚</span>
      </header>
      {stage === "input" ? (
        <InputStage
          draftText={draftText}
          scenario={scenario}
          onTextChange={setDraftText}
          onScenarioChange={selectScenario}
          onContinue={() => setStage("confirm")}
        />
      ) : null}
      {stage === "confirm" ? (
        <ConfirmationStage
          intent={intent}
          onIntentChange={setIntent}
          onBack={() => setStage("input")}
          onGenerate={() => setStage("route")}
        />
      ) : null}
      {stage === "route" ? (
        <RouteStage
          route={route}
          repairState={repairState}
          onBack={() => setStage("confirm")}
          onOpenRepair={() => setRepairState("review")}
          onCloseRepair={() => setRepairState("idle")}
          onApplyRepair={() => setRepairState("applied")}
        />
      ) : null}
    </main>
  );
}

function InputStage({
  draftText,
  scenario,
  onTextChange,
  onScenarioChange,
  onContinue,
}: {
  draftText: string;
  scenario: PrototypeScenario;
  onTextChange: (value: string) => void;
  onScenarioChange: (value: PrototypeScenario) => void;
  onContinue: () => void;
}) {
  return <section className={styles.inputStage} aria-labelledby="prototype-title">
    <div className={styles.inputIntro}>
      <p className={styles.kicker}>给我一句话就够了</p>
      <h1 id="prototype-title">这趟旅行，<br />你想怎么过？</h1>
      <p className={styles.lede}>说说目的地、天数、想去的地方或不能改的安排。剩下的，我们先替你理顺。</p>
    </div>
    <label className={styles.requestField}>
      <span>你的旅行想法</span>
      <textarea value={draftText} onChange={(event) => onTextChange(event.target.value)} aria-label="你的旅行想法" />
    </label>
    <div className={styles.exampleRow} aria-label="试试一个示例">
      {productResetFixtures.map((fixture) => <button key={fixture.id} type="button" className={scenario === fixture.id ? styles.exampleActive : styles.exampleButton} onClick={() => onScenarioChange(fixture.id)}>
        <strong>{fixture.label}</strong><span>{fixture.hint}</span>
      </button>)}
    </div>
    <button className={styles.primaryButton} type="button" onClick={onContinue}>看看我理解得对不对</button>
  </section>;
}

function ConfirmationStage({ intent, onIntentChange, onBack, onGenerate }: { intent: TripIntentSummary; onIntentChange: (value: TripIntentSummary) => void; onBack: () => void; onGenerate: () => void }) {
  const fixedText = intent.fixedEvents.map((event) => `${event.title} · ${event.startTime}–${event.endTime}`).join("；") || "暂无";
  return <section className={styles.confirmStage} aria-labelledby="confirm-title">
    <div className={styles.sectionHeading}>
      <div><p className={styles.kicker}>确认行程信息</p><h1 id="confirm-title">这次旅行，我这样理解。</h1></div>
      <button className={styles.textButton} type="button" onClick={onBack}>返回修改描述</button>
    </div>
    <div className={styles.confirmGrid}>
      <label><span>目的地</span><input value={intent.destination} onChange={(event) => onIntentChange({ ...intent, destination: event.target.value })} /></label>
      <label><span>玩几天</span><input type="number" min="1" max="7" value={intent.days} onChange={(event) => onIntentChange({ ...intent, days: Number(event.target.value) || 1 })} /></label>
      <label><span>想要的节奏</span><select value={intent.pace} onChange={(event) => onIntentChange({ ...intent, pace: event.target.value as TripIntentSummary["pace"] })}><option value="轻松">轻松</option><option value="适中">适中</option></select></label>
      <label><span>一定想去</span><input value={intent.mustVisit.join("、")} onChange={(event) => onIntentChange({ ...intent, mustVisit: event.target.value.split(/[、，,]/).map((value) => value.trim()).filter(Boolean) })} /></label>
      <label className={styles.wideField}><span>固定安排</span><input value={fixedText} readOnly aria-label="固定安排" /></label>
    </div>
    <details className={styles.details}><summary>查看系统理解依据</summary><ul>{intent.understandingNotes.map((note) => <li key={note}>{note}</li>)}</ul></details>
    <div className={styles.confirmAction}><p>这些信息可以继续改，生成后也能调整一小段路线。</p><button className={styles.primaryButton} type="button" onClick={onGenerate}>生成我的路线</button></div>
  </section>;
}

function RouteStage({ route, repairState, onBack, onOpenRepair, onCloseRepair, onApplyRepair }: { route: TripRoute; repairState: RepairState; onBack: () => void; onOpenRepair: () => void; onCloseRepair: () => void; onApplyRepair: () => void }) {
  const proposal = fixtureForScenario(route.trip.destination === "西安" ? "rushed" : "hangzhou").repair;
  const showRepair = route.trip.destination === "西安" && proposal;
  return <section className={styles.routeStage} aria-labelledby="route-title">
    <header className={styles.routeHeader}>
      <div><p className={styles.kicker}>你的路线</p><h1 id="route-title">{route.trip.destination}，{route.trip.days} 天。</h1><span>{route.trip.pace}一点，不把好时间都花在赶路上。</span></div>
      <button className={styles.textButton} type="button" onClick={onBack}>修改行程信息</button>
    </header>
    {route.risks.map((risk) => <aside className={styles.risk} key={risk.id}><strong>第 {risk.day} 天值得调整一下</strong><span>{risk.message}</span></aside>)}
    <nav className={styles.dayNav} aria-label="选择日期">{route.days.map((day) => <a key={day.day} href={`#day-${day.day}`}>DAY {day.day}</a>)}</nav>
    <div className={styles.dayStack}>
      {route.days.map((day) => <div key={day.day}>
        <DayTimeline day={day} route={route} />
        {showRepair && day.day === proposal.fromDay && repairState === "idle" ? <button className={styles.repairButton} type="button" onClick={onOpenRepair}>让这一天轻松一些</button> : null}
        {showRepair && day.day === proposal.fromDay && repairState === "review" ? <RepairReview proposal={proposal} route={route} onCancel={onCloseRepair} onApply={onApplyRepair} /> : null}
        {showRepair && day.day === proposal.fromDay && repairState === "applied" ? <p className={styles.localNotice}>{proposal.localOnlyNotice}</p> : null}
      </div>)}
    </div>
  </section>;
}

function DayTimeline({ day, route }: { day: TripRoute["days"][number]; route: TripRoute }) {
  return <article className={styles.day} id={`day-${day.day}`}>
    <header className={styles.dayHeader}><div><p>DAY {day.day}</p><h2>{day.title}</h2><span>{day.startLabel} · {day.endLabel}</span></div><div className={styles.load}><strong>{day.load.label}</strong><span>{day.load.activityCount} 个安排 · 移动约 {day.load.travelMinutes} 分钟</span></div></header>
    <ol className={styles.timeline}>
      {day.activities.map((activity) => <li key={activity.id}>
        <ActivityRow activity={activity} route={route} />
        {findTravelLeg(day, activity.id) ? <TravelRow leg={findTravelLeg(day, activity.id)!} /> : null}
      </li>)}
    </ol>
    <div className={styles.dayFooter}><p><strong>为什么这样安排</strong>{day.load.explanation}</p>{day.capacityNote ? <p><strong>可用余量</strong>{day.capacityNote}</p> : null}</div>
  </article>;
}

function ActivityRow({ activity, route }: { activity: Activity; route: TripRoute }) {
  const fixedEvent = findFixedEvent(route, activity);
  const sourceLabel = activity.source === "user_must" ? "你想去" : activity.source === "system_suggested" ? "顺路建议" : "已预约";
  return <div className={styles.activityRow}><time>{activity.startTime}<small>{activity.endTime}</small></time><div><div className={styles.activityTitle}><span className={`${styles.sourceMark} ${styles[`source_${activity.source}`]}`}>{sourceLabel}</span><h3>{activity.title}</h3>{fixedEvent ? <span className={styles.fixedBadge}>{fixedEvent.protectedLabel}</span> : null}</div><p>{activity.durationMinutes} 分钟 · {activity.reason}</p></div></div>;
}

function TravelRow({ leg }: { leg: ReturnType<typeof findTravelLeg> }) {
  if (!leg) return null;
  return <div className={styles.travelRow}><span>{travelModeCopy[leg.mode]}</span><p>下一段预计 {leg.durationMinutes} 分钟 · {leg.distanceLabel}</p></div>;
}

function RepairReview({ proposal, route, onCancel, onApply }: { proposal: NonNullable<ReturnType<typeof fixtureForScenario>["repair"]>; route: TripRoute; onCancel: () => void; onApply: () => void }) {
  const afterRoute = applyFixtureRepair(route, proposal);
  const beforeDay = route.days.find((day) => day.day === proposal.fromDay);
  const afterDay = afterRoute.days.find((day) => day.day === proposal.fromDay);
  return <section className={styles.repairReview} role="region" aria-label="调整前后对比">
    <p className={styles.kicker}>只调整一小段</p><h2>{proposal.title}</h2><p className={styles.repairLead}>把系统建议的“{proposal.movedActivityTitle}”放到第 {proposal.toDay} 天，不重新生成整趟旅行。</p>
    <div className={styles.compareColumns}><CompareDay title="调整前" day={beforeDay} /><CompareDay title="调整后" day={afterDay} /></div>
    <p className={styles.protection}>第 {proposal.toDay} 天仍有余量，会接住：{proposal.movedActivityTitle} · 16:20–17:20。</p>
    <p className={styles.protection}>这些安排不会动：{proposal.keepsProtected.join("、")}。</p>
    <div className={styles.repairActions}><button className={styles.textButton} type="button" onClick={onCancel}>暂不调整</button><button className={styles.primaryButton} type="button" onClick={onApply}>应用这次调整</button></div>
  </section>;
}

function CompareDay({ title, day }: { title: string; day: TripRoute["days"][number] | undefined }) {
  return <article><p>{title}</p><strong>{day?.load.activityCount ?? 0} 个安排 · 移动约 {day?.load.travelMinutes ?? 0} 分钟</strong><ul>{day?.activities.map((activity) => <li key={activity.id}>{activity.title}</li>)}</ul></article>;
}

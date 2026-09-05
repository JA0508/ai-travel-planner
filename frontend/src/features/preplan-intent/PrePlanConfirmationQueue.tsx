import { useState, type ReactNode } from "react";
import type { FixedEventIntent, IntentClarification, PlaceIdentity, PlaceResolutionOption } from "@/features/intent-confirmation/intentTypes";
import type { ConfirmationItem, ConfirmedItem } from "./prePlanConfirmationModel";

type Props = {
  items: ConfirmationItem[];
  confirmedItems: ConfirmedItem[];
  identities: PlaceIdentity[];
  events: FixedEventIntent[];
  questions: IntentClarification[];
  busy: boolean;
  onConfirmPlace: (identity: PlaceIdentity, option: PlaceResolutionOption) => void;
  onUpdateFixedLocation: (event: FixedEventIntent, location: string) => void;
  renderClarification: (question: IntentClarification) => ReactNode;
};

export function PrePlanConfirmationQueue({
  items,
  confirmedItems,
  identities,
  events,
  questions,
  busy,
  onConfirmPlace,
  onUpdateFixedLocation,
  renderClarification,
}: Props) {
  const questionById = new Map(questions.map((question) => [question.question_id, question]));
  const remainingCopy = items.length ? `还需确认 ${items.length} 项` : "可以生成首版路线";

  return (
    <section className="uc-confirmation-workbench" aria-label="确认清单" aria-live="polite">
      <div className="uc-confirmation-workbench-heading">
        <div>
          <p>确认清单</p>
          <h2>{remainingCopy}</h2>
        </div>
        <span>{items.length ? "每完成一项，路线就更可靠" : "关键信息已齐备"}</span>
      </div>

      {items.length ? <section className="uc-confirmation-lane uc-confirmation-lane--todo" aria-label="还需确认">
        <div className="uc-confirmation-lane-heading"><span>01</span><div><p>还需确认</p><h3>只处理会影响这版路线的项目</h3></div></div>
        <div className="uc-confirmation-items">
          {items.map((item) => <ConfirmationItemCard
            key={item.id}
            item={item}
            identity={item.kind === "must_place" || item.kind === "fixed_place" ? identities.find((identity) => identity.stable_id === item.identityId) ?? null : null}
            event={item.kind === "fixed_place" ? events.find((event) => event.event_id === item.eventId) ?? null : null}
            question={item.kind === "clarification" || item.kind === "conflict" ? item.questionId ? questionById.get(item.questionId) ?? null : null : null}
            busy={busy}
            onConfirmPlace={onConfirmPlace}
            onUpdateFixedLocation={onUpdateFixedLocation}
            renderClarification={renderClarification}
          />)}
        </div>
      </section> : null}

      <section className="uc-confirmation-lane uc-confirmation-lane--confirmed" aria-label="已确认">
        <div className="uc-confirmation-lane-heading"><span>{items.length ? "02" : "01"}</span><div><p>已确认</p><h3>这些信息会作为路线依据保留</h3></div></div>
        {confirmedItems.length ? (
          <ul className="uc-confirmation-confirmed-list">
            {confirmedItems.map((item) => <li key={item.id}><strong>{item.title}</strong><span>{item.detail}</span></li>)}
          </ul>
        ) : (
          <p className="uc-confirmation-muted">完成上面的确认后，地点和固定安排会出现在这里。</p>
        )}
      </section>
    </section>
  );
}

function ConfirmationItemCard({
  item,
  identity,
  event,
  question,
  busy,
  onConfirmPlace,
  onUpdateFixedLocation,
  renderClarification,
}: {
  item: ConfirmationItem;
  identity: PlaceIdentity | null;
  event: FixedEventIntent | null;
  question: IntentClarification | null;
  busy: boolean;
  onConfirmPlace: Props["onConfirmPlace"];
  onUpdateFixedLocation: Props["onUpdateFixedLocation"];
  renderClarification: Props["renderClarification"];
}) {
  if (item.kind === "clarification" && question) return <div className="uc-confirmation-item">{renderClarification(question)}</div>;
  if (item.kind === "conflict") return <article className="uc-confirmation-item uc-confirmation-item--conflict"><h4>{item.title}</h4><p>{item.detail}</p></article>;

  return <article className="uc-confirmation-item">
    <div className="uc-confirmation-item-copy"><h4>{item.title}</h4><p>{item.detail}</p></div>
    {identity?.confirmation_options.length ? <div className="uc-confirmation-choice" aria-label={`${item.title}的地点候选`}>
      {identity.confirmation_options.map((option) => <button key={option.provider_place_id} type="button" disabled={busy} onClick={() => onConfirmPlace(identity, option)}><strong>{option.canonical_name}</strong><small>{option.address_summary ?? option.category ?? "地点信息"}</small></button>)}
    </div> : null}
    {item.kind === "fixed_place" && event ? <FixedLocationPrompt event={event} busy={busy} onSave={onUpdateFixedLocation} /> : null}
    {item.kind === "must_place" && !identity?.confirmation_options.length ? <p className="uc-confirmation-muted">暂时没有可供确认的地点候选。请重新整理旅行信息，或补充更具体的地标。</p> : null}
  </article>;
}

function FixedLocationPrompt({ event, busy, onSave }: { event: FixedEventIntent; busy: boolean; onSave: (event: FixedEventIntent, location: string) => void }) {
  const [location, setLocation] = useState(event.location_text ?? "");
  const inputId = `fixed-location-${event.event_id}`;
  return <div className="uc-confirmation-location"><label htmlFor={inputId}>预约地点</label><input id={inputId} value={location} onChange={(input) => setLocation(input.target.value)} placeholder="例如：上海博物馆" disabled={busy} /><button type="button" className="uc-intent-secondary" disabled={busy || !location.trim()} onClick={() => onSave(event, location)}>保存地点</button></div>;
}

import React, { useEffect, useMemo, useRef, useState, type FormEvent, type ReactNode } from "react";
import type { FixedEventIntent, IntentClarification, PlaceIdentity, PlaceResolutionOption } from "@/features/intent-confirmation/intentTypes";
import type { ConfirmationItem, ConfirmedItem } from "./prePlanConfirmationModel";
import type { PlaceIdentitySuggestionSearchResult, PrePlanPlaceIdentitySuggestionsResponse } from "./draftIntentEditApi";

export type PlaceConfirmationFocusRequest = {
  requestId: number;
  kind: "must_place" | "fixed_place";
  fieldId?: string;
  stableId?: string;
};

export function shouldKeepPreviousPlaceSearchSuggestions(
  suggestions: PrePlanPlaceIdentitySuggestionsResponse | null,
  query: string,
): boolean {
  return suggestions?.query === query.trim();
}

export function centeredConfirmationScrollTop(
  target: Pick<DOMRect, "top" | "height">,
  currentScrollY: number,
  viewportHeight: number,
): number {
  const safeCurrentScrollY = Number.isFinite(currentScrollY) ? Math.max(0, currentScrollY) : 0;
  const safeViewportHeight = Number.isFinite(viewportHeight) ? Math.max(0, viewportHeight) : 0;
  const safeTargetTop = Number.isFinite(target.top) ? target.top : 0;
  const safeTargetHeight = Number.isFinite(target.height) ? Math.max(0, target.height) : 0;
  const centeredOffset = Math.max(0, (safeViewportHeight - safeTargetHeight) / 2);

  return Math.max(0, Math.round(safeCurrentScrollY + safeTargetTop - centeredOffset));
}

export function findPlaceFocusItem(
  items: ConfirmationItem[],
  request: PlaceConfirmationFocusRequest | undefined,
  events: FixedEventIntent[],
): ConfirmationItem | null {
  if (!request) return null;

  if (request.stableId) {
    return items.find((item) => (
      item.kind === "must_place"
      && request.kind === "must_place"
      && item.identityId === request.stableId
    )) ?? null;
  }

  if (request.fieldId) {
    return items.find((item) => {
      if (item.kind !== request.kind) return false;
      const event = item.kind === "fixed_place" ? events.find((candidate) => candidate.event_id === item.eventId) : null;
      return event?.metadata.field_id === request.fieldId;
    }) ?? null;
  }

  return items.find((item) => item.kind === request.kind) ?? null;
}

export function placeFocusUnavailableMessage(
  request: PlaceConfirmationFocusRequest | undefined,
  item: ConfirmationItem | null,
): string | null {
  if (!request || item || (!request.stableId && !request.fieldId)) return null;

  return "要确认的地点已更新，系统没有替你改选其他地点。请查看当前仍待确认的项目。";
}

type Props = {
  items: ConfirmationItem[];
  confirmedItems: ConfirmedItem[];
  identities: PlaceIdentity[];
  events: FixedEventIntent[];
  questions: IntentClarification[];
  busy: boolean;
  canGeneratePreview: boolean;
  placeFocusRequest?: PlaceConfirmationFocusRequest;
  onModifyRequest: () => void;
  onConfirmPlace: (identity: PlaceIdentity, option: PlaceResolutionOption, searchQuery?: string) => void;
  onSearchPlace: (identity: PlaceIdentity, query: string) => Promise<PlaceIdentitySuggestionSearchResult>;
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
  canGeneratePreview,
  placeFocusRequest,
  onModifyRequest,
  onConfirmPlace,
  onSearchPlace,
  onUpdateFixedLocation,
  renderClarification,
}: Props) {
  const questionById = useMemo(() => new Map(questions.map((question) => [question.question_id, question])), [questions]);
  const blockedWithoutAction = !canGeneratePreview && items.length === 0;
  const remainingCopy = items.length
    ? `还需确认 ${items.length} 项`
    : blockedWithoutAction
      ? "还需要检查需求"
      : "可以生成首版路线";
  const actionableItems = useMemo(
    () => items.filter((item) => isActionableItem(item, identities, events, questionById)),
    [events, identities, items, questionById],
  );
  const [expandedItemId, setExpandedItemId] = useState<string | null>(() => actionableItems[0]?.id ?? null);
  const completedPlaceItemIdRef = useRef<string | null>(null);
  const confirmationHeadingRef = useRef<HTMLHeadingElement>(null);

  useEffect(() => {
    setExpandedItemId((current) => (
      current && actionableItems.some((item) => item.id === current)
        ? current
        : actionableItems[0]?.id ?? null
    ));
  }, [actionableItems]);

  useEffect(() => {
    const completedItemId = completedPlaceItemIdRef.current;
    if (!completedItemId || items.some((item) => item.id === completedItemId)) return;
    completedPlaceItemIdRef.current = null;
    const nextItem = actionableItems[0] ?? null;
    if (nextItem) setExpandedItemId(nextItem.id);
    const frame = window.requestAnimationFrame(() => {
      if (nextItem) {
        const nextTarget = document.getElementById(`confirmation-item-${nextItem.id}`);
        if (nextTarget) focusPlaceConfirmationAction(nextTarget);
        return;
      }
      confirmationHeadingRef.current?.focus();
    });
    return () => window.cancelAnimationFrame(frame);
  }, [actionableItems, items]);

  function onPlaceConfirmationStart(itemId: string) {
    completedPlaceItemIdRef.current = itemId;
  }

  const placeFocusItem = findPlaceFocusItem(actionableItems, placeFocusRequest, events);
  const placeFocusItemId = placeFocusItem?.id ?? null;
  const placeFocusNotice = placeFocusUnavailableMessage(placeFocusRequest, placeFocusItem);

  useEffect(() => {
    if (!placeFocusRequest) return;
    if (!placeFocusItemId) {
      if (!placeFocusNotice) return;
      const frame = window.requestAnimationFrame(() => confirmationHeadingRef.current?.focus());
      return () => window.cancelAnimationFrame(frame);
    }
    setExpandedItemId(placeFocusItemId);
    const frame = window.requestAnimationFrame(() => {
      const target = document.getElementById(`confirmation-item-${placeFocusItemId}`);
      if (!target) return;
      window.scrollTo({
        top: centeredConfirmationScrollTop(target.getBoundingClientRect(), window.scrollY, window.innerHeight),
        behavior: "smooth",
      });
      focusPlaceConfirmationAction(target);
    });
    return () => window.cancelAnimationFrame(frame);
  }, [placeFocusItemId, placeFocusNotice, placeFocusRequest?.requestId]);

  return (
    <section className="uc-confirmation-workbench" aria-label="确认清单">
      <p className="uc-intent-sr-only" role="status" aria-atomic="true">
        确认清单更新：{remainingCopy}。
      </p>
      <div className="uc-confirmation-workbench-heading">
        <div>
          <p>确认清单</p>
          <h2 ref={confirmationHeadingRef} tabIndex={-1}>{remainingCopy}</h2>
          {placeFocusNotice ? <p className="uc-confirmation-muted" role="status">{placeFocusNotice}</p> : null}
        </div>
        <span>{items.length ? "每完成一项，路线就更可靠" : blockedWithoutAction ? "请先补齐路线条件" : "关键信息已齐备"}</span>
      </div>

      {blockedWithoutAction ? <div className="uc-confirmation-recovery"><p className="uc-confirmation-muted">当前没有可直接确认的项目。请补充或校正路线条件后再继续。</p><button type="button" className="uc-intent-secondary" onClick={onModifyRequest} disabled={busy}>修改原始需求</button></div> : null}

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
            expanded={expandedItemId === item.id}
            actionable={actionableItems.some((actionableItem) => actionableItem.id === item.id)}
            onToggle={() => setExpandedItemId((current) => current === item.id ? null : item.id)}
            onPlaceConfirmationStart={onPlaceConfirmationStart}
            onConfirmPlace={onConfirmPlace}
            onSearchPlace={onSearchPlace}
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
          <p className="uc-confirmation-muted">{blockedWithoutAction ? "补齐路线条件后，确认的地点和固定安排会出现在这里。" : "完成上面的确认后，地点和固定安排会出现在这里。"}</p>
        )}
      </section>
    </section>
  );
}

function focusPlaceConfirmationAction(target: HTMLElement) {
  target
    .querySelector<HTMLElement>(".uc-place-accept, .uc-place-search-toggle, input, .uc-confirmation-item-action")
    ?.focus({ preventScroll: true });
}

function ConfirmationItemCard({
  item,
  identity,
  event,
  question,
  busy,
  expanded,
  actionable,
  onToggle,
  onPlaceConfirmationStart,
  onConfirmPlace,
  onSearchPlace,
  onUpdateFixedLocation,
  renderClarification,
}: {
  item: ConfirmationItem;
  identity: PlaceIdentity | null;
  event: FixedEventIntent | null;
  question: IntentClarification | null;
  busy: boolean;
  expanded: boolean;
  actionable: boolean;
  onToggle: () => void;
  onPlaceConfirmationStart: (itemId: string) => void;
  onConfirmPlace: Props["onConfirmPlace"];
  onSearchPlace: Props["onSearchPlace"];
  onUpdateFixedLocation: Props["onUpdateFixedLocation"];
  renderClarification: Props["renderClarification"];
}) {
  if (item.kind === "clarification" && question) {
    return <div id={`confirmation-item-${item.id}`} className="uc-confirmation-item">
      <ConfirmationItemCopy item={item} />
      {actionable ? <ConfirmationItemToggle item={item} expanded={expanded} busy={busy} onToggle={onToggle} /> : null}
      {expanded ? <div id={`confirmation-item-editor-${item.id}`} className="uc-confirmation-item-editor">{renderClarification(question)}</div> : null}
    </div>;
  }
  if (item.kind === "conflict") return <article id={`confirmation-item-${item.id}`} className="uc-confirmation-item uc-confirmation-item--conflict"><h4>{item.title}</h4><p>{item.detail}</p></article>;

  return <article id={`confirmation-item-${item.id}`} className="uc-confirmation-item">
    <ConfirmationItemCopy item={item} />
    {actionable ? <ConfirmationItemToggle item={item} expanded={expanded} busy={busy} onToggle={onToggle} /> : null}
    {expanded ? <div id={`confirmation-item-editor-${item.id}`} className="uc-confirmation-item-editor">
      {identity ? <PlaceIdentityRecommendation
        identity={identity}
        title={item.title}
        busy={busy}
        onConfirm={(confirmedIdentity, option, searchQuery) => {
          onPlaceConfirmationStart(item.id);
          onConfirmPlace(confirmedIdentity, option, searchQuery);
        }}
        onSearch={onSearchPlace}
      /> : null}
      {item.kind === "fixed_place" && event && !identity ? <FixedLocationPrompt event={event} busy={busy} onSave={onUpdateFixedLocation} /> : null}
    </div> : null}
  </article>;
}

function isActionableItem(
  item: ConfirmationItem,
  identities: PlaceIdentity[],
  events: FixedEventIntent[],
  questionById: Map<string, IntentClarification>,
): boolean {
  if (item.kind === "conflict") return false;
  if (item.kind === "clarification") return Boolean(item.questionId && questionById.has(item.questionId));
  if (item.kind === "must_place") return identities.some((identity) => identity.stable_id === item.identityId);
  if (item.kind === "fixed_place") return events.some((event) => event.event_id === item.eventId);
  return false;
}

function ConfirmationItemCopy({ item }: { item: ConfirmationItem }) {
  return <div className="uc-confirmation-item-copy"><h4>{item.title}</h4><p>{item.detail}</p></div>;
}

function ConfirmationItemToggle({ item, expanded, busy, onToggle }: { item: ConfirmationItem; expanded: boolean; busy: boolean; onToggle: () => void }) {
  const label = expanded ? "收起" : item.kind === "fixed_place" ? "补充地点" : item.kind === "must_place" ? "选择地点" : "处理这项";
  const panelId = `confirmation-item-editor-${item.id}`;
  return <button
    type="button"
    className="uc-confirmation-item-action"
    aria-expanded={expanded}
    aria-controls={expanded ? panelId : undefined}
    disabled={busy}
    onClick={onToggle}
  >{label}</button>;
}

function PlaceIdentityRecommendation({
  identity,
  title,
  busy,
  onConfirm,
  onSearch,
}: {
  identity: PlaceIdentity;
  title: string;
  busy: boolean;
  onConfirm: Props["onConfirmPlace"];
  onSearch: Props["onSearchPlace"];
}) {
  const [searchOpen, setSearchOpen] = useState(false);
  const [query, setQuery] = useState(identity.original_name);
  const [suggestions, setSuggestions] = useState<PrePlanPlaceIdentitySuggestionsResponse | null>(null);
  const [searching, setSearching] = useState(false);
  const [searchMessage, setSearchMessage] = useState<string | null>(null);
  const [searchError, setSearchError] = useState<{ message: string; retryable: boolean; keptPreviousSuggestions: boolean } | null>(null);
  const options = suggestions?.options ?? identity.confirmation_options;
  const recommendedId = suggestions?.recommended_provider_place_id ?? options[0]?.provider_place_id ?? null;
  const recommended = options.find((option) => option.provider_place_id === recommendedId) ?? null;
  const alternatives = searchOpen ? options.filter((option) => option.provider_place_id !== recommended?.provider_place_id) : [];
  const reason = suggestions?.recommendation_reason ?? (recommended ? "基于地点名称和本次目的地的提供商检索排序。" : null);

  async function runSearch() {
    const trimmed = query.trim();
    if (!trimmed || searching || busy) return;
    const previousSuggestionsMatchQuery = shouldKeepPreviousPlaceSearchSuggestions(suggestions, trimmed);
    setSearching(true);
    setSearchMessage(null);
    setSearchError(null);
    if (!previousSuggestionsMatchQuery) setSuggestions(null);
    const result = await onSearch(identity, trimmed);
    setSearching(false);
    if (result.kind === "success") {
      setSuggestions(result.suggestions);
      setSearchMessage(
        result.suggestions.options.length
          ? `已找到 ${result.suggestions.options.length} 个地点候选。`
          : `没有找到「${trimmed}」对应的地点。试试补充城市、街区、附近地标或准确地址。`,
      );
      return;
    }
    const keptPreviousSuggestions = result.retryable && previousSuggestionsMatchQuery;
    if (!keptPreviousSuggestions) setSuggestions(null);
    setSearchError({ message: result.message, retryable: result.retryable, keptPreviousSuggestions });
  }

  function submitSearch(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    void runSearch();
  }

  return <div className="uc-place-identity-editor" aria-label={`${title}的地点确认`}>
    {recommended ? <section className="uc-place-recommendation" aria-label="系统推荐地点">
      <p>系统推荐</p>
      <strong>{recommended.canonical_name}</strong>
      <span>{recommended.address_summary ?? recommended.category ?? "提供商地点候选"}</span>
      {reason ? <small>推荐依据：{reason}</small> : null}
      <button type="button" className="uc-place-accept" disabled={busy || searching} onClick={() => onConfirm(identity, recommended, suggestions?.query)}>采用这个地点</button>
    </section> : <p className="uc-confirmation-muted">暂时没有可确认的地点候选。你可以搜索更具体的地标或街区名称。</p>}

    <button type="button" className="uc-place-search-toggle" disabled={busy} aria-expanded={searchOpen} onClick={() => setSearchOpen((open) => !open)}>{recommended ? "换一个 / 搜索地点" : "搜索地点"}</button>
    {searchOpen ? <div className="uc-place-search-panel">
      <form className="uc-place-search-form" onSubmit={submitSearch}>
        <label htmlFor={`place-search-${identity.stable_id}`}>搜索更具体的地点</label>
        <div><input id={`place-search-${identity.stable_id}`} value={query} onChange={(event) => setQuery(event.target.value)} placeholder="例如：十八梯、解放碑附近" maxLength={160} disabled={busy || searching} /><button type="submit" className="uc-intent-secondary" disabled={busy || searching || !query.trim()}>{searching ? "搜索中…" : "搜索"}</button></div>
      </form>
      {searchError ? <><p className="uc-place-search-error" role="alert">{searchError.message}{searchError.retryable ? searchError.keptPreviousSuggestions ? " 已保留上次查询的候选；采用时会再次核验。" : " 你可以直接重新搜索，当前行程没有变化。" : " 请换一个更具体的地点名称后再试。"}</p>{searchError.retryable ? <button type="button" className="uc-intent-secondary" disabled={busy || searching || !query.trim()} onClick={() => void runSearch()}>重新搜索</button> : null}</> : null}
      {searchMessage ? <p className="uc-place-search-status" role="status">{searchMessage}</p> : null}
      {alternatives.length ? <div className="uc-confirmation-choice" aria-label={`${title}的其他地点候选`}>
        {alternatives.map((option) => <button key={option.provider_place_id} type="button" disabled={busy || searching} onClick={() => onConfirm(identity, option, suggestions?.query)}><strong>{option.canonical_name}</strong><small>{option.address_summary ?? option.category ?? "提供商地点候选"}</small></button>)}
      </div> : null}
    </div> : null}
  </div>;
}

function FixedLocationPrompt({ event, busy, onSave }: { event: FixedEventIntent; busy: boolean; onSave: (event: FixedEventIntent, location: string) => void }) {
  const [location, setLocation] = useState(event.location_text ?? "");
  const inputId = `fixed-location-${event.event_id}`;
  return <div className="uc-confirmation-location"><label htmlFor={inputId}>预约地点</label><input id={inputId} value={location} onChange={(input) => setLocation(input.target.value)} placeholder="例如：上海博物馆" disabled={busy} /><button type="button" className="uc-intent-secondary" disabled={busy || !location.trim()} onClick={() => onSave(event, location)}>保存地点</button></div>;
}

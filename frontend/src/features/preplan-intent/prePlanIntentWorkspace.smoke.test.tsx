import assert from "node:assert/strict";
import test from "node:test";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { PrePlanIntentWorkspace } from "./PrePlanIntentWorkspace";
import { PrePlanConfirmationQueue, shouldKeepPreviousPlaceSearchSuggestions } from "./PrePlanConfirmationQueue";

const componentPath = fileURLToPath(new URL("./PrePlanIntentWorkspace.tsx", import.meta.url));
const queuePath = fileURLToPath(new URL("./PrePlanConfirmationQueue.tsx", import.meta.url));
const stylesPath = fileURLToPath(new URL("../../app/globals.css", import.meta.url));

test("the primary source-refresh action starts a new compile attempt without bypassing confirmation", () => {
  const source = readFileSync(componentPath, "utf8");
  const handler = source.slice(source.indexOf("function handlePrimaryAction()"), source.indexOf("return (", source.indexOf("function handlePrimaryAction()")));
  assert.match(handler, /if \(!view \|\| busy\) return/);
  assert.match(handler, /primaryAction.kind === "refresh_intent"[\s\S]*compileIntent\(\{ startNewAttempt: true \}\);\s*return;/);
  assert.doesNotMatch(handler, /void apply\(/);
});

test("pre-plan workspace starts with a plain-language confirmation surface", () => {
  const html = renderToStaticMarkup(
    <PrePlanIntentWorkspace
      tripId="trip_draft_1"
      directUserText="我想去西安玩三天，白天看历史景点，晚上吃东西。"
      onCancel={() => undefined}
      onApplied={() => undefined}
    />,
  );
  assert.match(html, /确认行程信息/);
  assert.match(html, /确认几个关键信息后，我们会为你生成第一版行程/);
  assert.match(html, /正在整理你的旅行需求/);
  assert.doesNotMatch(html, /Intent Contract/);
  assert.doesNotMatch(html, /field_path/);
  assert.doesNotMatch(html, /provenance graph/i);
});

test("the summary does not promise an in-page confirmation when only request edits can resolve a blocker", () => {
  const source = readFileSync(componentPath, "utf8");

  assert.match(source, /view\.requiresTravelInformationEdit \? "请修改旅行信息"/);
  assert.doesNotMatch(source, /view\.canGeneratePreview \? "可以开始规划" : `还差 \$\{view\.remainingConfirmationCount\} 项`/);
});

test("pre-plan bootstrap restores an existing intent before compiling a new Draft revision", () => {
  const source = readFileSync(componentPath, "utf8");
  assert.match(source, /autoCompileTripRef/);
  assert.match(source, /compileInFlightRef/);
  assert.match(source, /void bootstrapIntent\(\)/);
  assert.match(source, /if \(result\.ok\) \{[\s\S]*hydrateLatestIntent\(result\.data\)/);
  assert.match(source, /if \(result\.code === "intent_edit_no_longer_applicable"\) \{[\s\S]*await compileIntent\(\)/);
  assert.match(source, /void compileIntent\(\)/);
  assert.doesNotMatch(source, /编译意图合同/);
  assert.doesNotMatch(source, /field\.field_path/);
  assert.doesNotMatch(source, /semantic_digest/);
  assert.doesNotMatch(source, /provenance_graph/);
  assert.match(source, /确认行程信息/);
  assert.match(source, /PrePlanConfirmationQueue/);
  assert.match(source, /我先按你的描述整理好了/);
  assert.match(source, /查看依据/);
  assert.match(source, /重新识别/);
  assert.match(source, /onClick=\{onRefresh\} disabled=\{busy\}>重新整理旅行信息<\/button>/);
});

test("pre-plan workspace connects critical edits and clarification answers to server state", () => {
  const source = readFileSync(componentPath, "utf8");
  assert.match(source, /update_destination/);
  assert.doesNotMatch(source, /clarificationTitle\(/);
  assert.match(source, /update_date_policy/);
  assert.match(source, /update_trip_days/);
  assert.match(source, /update_pace/);
  assert.match(source, /resolvePrePlanIntentClarification/);
  assert.match(source, /base_draft_version/);
  assert.match(source, /X-Idempotency-Key/);
  assert.match(source, /网络连接失败，你的修改还在这里/);
  assert.match(source, /行程信息已经在其他页面更新/);
  assert.match(source, /重新应用我的修改/);
  assert.match(source, /restoreFocusAfterSuccess/);
  assert.match(source, /preplan-primary-action/);
  assert.match(source, /getLatestPrePlanIntent/);
  assert.doesNotMatch(source, /localStorage/);
});

test("confirmation queue advances reading focus after a confirmed place leaves the queue", () => {
  const source = readFileSync(queuePath, "utf8");

  assert.match(source, /completedPlaceItemIdRef/);
  assert.match(source, /onPlaceConfirmationStart/);
  assert.match(source, /items\.some\(\(item\) => item\.id === completedItemId\)/);
  assert.match(source, /setExpandedItemId\(nextItem\.id\)/);
  assert.match(
    source,
    /if \(nextTarget\) \{[\s\S]*window\.scrollTo\(\{[\s\S]*centeredConfirmationScrollTop\(nextTarget\.getBoundingClientRect\(\), window\.scrollY, window\.innerHeight\)[\s\S]*focusPlaceConfirmationAction\(nextTarget\)/,
  );
  assert.match(source, /focusPlaceConfirmationAction\(nextTarget\)/);
  assert.match(source, /confirmationHeadingRef\.current\?\.focus\(\)/);
});

test("pre-plan preview refreshes the latest Draft after a stale response", () => {
  const source = readFileSync(componentPath, "utf8");
  assert.match(source, /if \(isStalePrePlanIntentError\(result\.code\)\) \{[\s\S]*await refreshLatestIntent\(\)/);
  assert.match(source, /已载入最新行程信息，请重新生成路线预览/);
});

test("pre-plan preview ends a slow request with a clear retry state", () => {
  const source = readFileSync(componentPath, "utf8");
  assert.match(source, /PREVIEW_REQUEST_TIMEOUT_MS/);
  assert.match(source, /AbortController/);
  assert.match(source, /previewTimedOutMessage\(\)/);
});

test("pre-plan preview gives recoverable failures a direct retry instruction", () => {
  const source = readFileSync(componentPath, "utf8");
  assert.match(source, /result\.recoverable \|\| !result\.code/);
  assert.match(source, /previewUnavailableMessage\(\)/);
});

test("pre-plan preview provides a separate retry action after a recoverable failure", () => {
  const source = readFileSync(componentPath, "utf8");
  assert.match(source, /action: "retry_preview"/);
  assert.match(source, /feedback\.action === "retry_preview"[\s\S]*onClick=\{\(\) => void buildPreview\(\)\}/);
});

test("first route preview is revealed and focused after it is generated", () => {
  const source = readFileSync(componentPath, "utf8");

  assert.match(source, /setPreview\(result\.data\);[\s\S]*setRevealPreview\(true\)/);
  assert.match(source, /window\.scrollTo/);
  assert.match(source, /previewRevealScrollTop/);
  assert.doesNotMatch(source, /scrollIntoView/);
  assert.match(source, /target\.focus\(\{ preventScroll: true \}\)/);
  assert.match(source, /aria-label="第一版路线预览"/);
});

test("ready route previews explain that confirmation creates the formal itinerary", () => {
  const source = readFileSync(componentPath, "utf8");

  assert.match(source, /draftConfirmation=\{\{/);
  assert.match(source, /label: operation === "applying" \? "正在保存行程……" : feedback\?\.action === "retry_apply" \? "重新保存正式行程" : "确认并生成行程"/);
  assert.match(source, /hint: "确认后会保存为正式行程，之后仍可修改。"/);
  assert.match(source, /recoveryMessage: feedback\?\.action === "retry_apply" \? feedback\.message : undefined/);
  assert.match(source, /onConfirm: \(\) => void apply\(\)/);
});

test("recoverable formal-itinerary saves keep the preview and expose a direct retry", () => {
  const source = readFileSync(componentPath, "utf8");

  assert.match(source, /savePreviewUnavailableMessage\(\)/);
  assert.match(source, /action: "retry_apply"/);
  assert.match(source, /feedback && !\(preview && feedback\.action === "retry_apply"\)/);
});

test("pre-plan preview exposes a matching inline edit for a repairable planning blocker", () => {
  const source = readFileSync(componentPath, "utf8");
  assert.match(source, /plannerHandoffRecoveryAction\(result\.code, result\.context\)/);
  assert.match(source, /feedback\.action === "edit_date_policy"[\s\S]*openEditor\("date_policy"\)/);
});

test("pre-plan preview gives changed place facts a direct safe refresh action", () => {
  const source = readFileSync(componentPath, "utf8");
  assert.match(source, /feedback\.action === "refresh_intent"[\s\S]*compileIntent\(\{ startNewAttempt: true \}\)/);
  assert.match(source, /重新整理旅行信息/);
});

test("pre-plan preview can take a blocked direct place to its confirmation control", () => {
  const source = readFileSync(componentPath, "utf8");
  const queueSource = readFileSync(queuePath, "utf8");
  assert.match(source, /feedback\.action === "focus_place_confirmation"[\s\S]*requestPlaceConfirmationFocus\("must_place", \{ stableId: feedback\.actionPlaceStableId \}\)/);
  assert.match(source, /placeFocusRequest=\{placeConfirmationFocusRequest \?\? undefined\}/);
  assert.match(queueSource, /placeFocusRequest/);
  assert.match(queueSource, /window\.scrollTo/);
  assert.doesNotMatch(queueSource, /scrollIntoView/);
  assert.match(source, /plannerHandoffRecoveryPlaceStableId\(action, result\.context\)/);
  assert.match(queueSource, /findPlaceFocusItem\(actionableItems, placeFocusRequest, events\)/);
  assert.match(queueSource, /item\.identityId === request\.stableId/);
  assert.match(queueSource, /placeFocusUnavailableMessage\(placeFocusRequest, placeFocusItem\)/);
  assert.match(queueSource, /要确认的地点已更新/);
});

test("pre-plan preview names the still-current must-place that blocks it", () => {
  const source = readFileSync(componentPath, "utf8");
  assert.match(source, /find\(\(identity\) => identity\.stable_id === actionPlaceStableId\)/);
  assert.match(source, /result\.context,\s*actionPlaceName,/);
});

test("pre-plan preview can take a blocked fixed arrangement to its location confirmation", () => {
  const source = readFileSync(componentPath, "utf8");
  const queueSource = readFileSync(queuePath, "utf8");
  assert.match(source, /feedback\.action === "focus_fixed_place_confirmation"[\s\S]*requestPlaceConfirmationFocus\("fixed_place", \{ fieldId: feedback\.actionFieldId \}\)/);
  assert.match(queueSource, /item\.kind !== request\.kind/);
  assert.match(source, /plannerHandoffRecoveryFieldId\(action, result\.context\)/);
  assert.match(queueSource, /event\?\.metadata\.field_id === request\.fieldId/);
});

test("blocked place recovery focuses the next confirmation action instead of the collapse control", () => {
  const queueSource = readFileSync(queuePath, "utf8");

  assert.match(queueSource, /focusPlaceConfirmationAction\(target\)/);
  assert.match(queueSource, /\.uc-place-accept, \.uc-place-search-toggle, input, \.uc-confirmation-item-action/);
  assert.match(queueSource, /focus\(\{ preventScroll: true \}\)/);
  assert.doesNotMatch(queueSource, /target\?\.querySelector<HTMLButtonElement>\("button"\)\?\.focus\(\)/);
});

test("explicitly reprocessing travel information starts a fresh idempotent compile attempt", () => {
  const source = readFileSync(componentPath, "utf8");
  assert.match(source, /compileIntent\(\{ startNewAttempt: true \}\)/);
  assert.match(source, /resolvePrePlanCompileAttempt\(/);
});

test("pre-plan workspace uses one editorial confirmation queue instead of repeated blocker cards", () => {
  const source = readFileSync(componentPath, "utf8");
  const queueSource = readFileSync(queuePath, "utf8");

  assert.match(source, /PrePlanConfirmationQueue/);
  assert.match(source, /已理解/);
  assert.match(source, /修改原始需求/);
  assert.match(queueSource, /还需确认/);
  assert.match(queueSource, /已确认/);
  assert.match(queueSource, /confirmation_options/);
  assert.match(queueSource, /onConfirmPlace/);
  assert.match(queueSource, /系统推荐/);
  assert.match(queueSource, /采用这个地点/);
  assert.match(queueSource, /换一个\s*\/\s*搜索地点/);
  assert.match(source, /getPrePlanPlaceIdentitySuggestions/);
  assert.match(source, /place_identity_provider_unavailable/);
  assert.match(source, /当前地点尚未确认/);
  assert.match(source, /result\.recoverable \|\| !result\.code/);
  assert.match(source, /feedbackScope === "workspace"/);
  assert.match(queueSource, /role="alert"/);
  assert.match(source, /地点服务暂时不可用/);
  assert.match(queueSource, /setSuggestions\(null\);[\s\S]*const result = await onSearch/);
  assert.match(queueSource, /searchError\.retryable[\s\S]*重新搜索/);
  assert.match(queueSource, /onClick=\{\(\) => void runSearch\(\)\}/);
  assert.match(queueSource, /没有找到「\$\{trimmed\}」对应的地点/);
  assert.match(queueSource, /补充城市、街区、附近地标或准确地址/);
  assert.doesNotMatch(source, /function FixedPlaceConfirmation/);
  assert.doesNotMatch(source, /function MustPlaceConfirmation/);
  assert.doesNotMatch(source, /function FixedArrangementSummary/);
});

test("place confirmation distinguishes the traveler mention from the provider candidate", () => {
  const queueSource = readFileSync(queuePath, "utf8");

  assert.match(queueSource, /你提到的地点/);
  assert.match(queueSource, /尚未作为路线地点保存/);
  assert.match(queueSource, /提供商候选（系统推荐）/);
  assert.match(queueSource, /确认前不会加入路线/);
});

test("confirmation recovery carries an existing conflict reason back to the request editor", () => {
  const source = readFileSync(componentPath, "utf8");
  const queueSource = readFileSync(queuePath, "utf8");

  assert.match(source, /onCancel: \(notice\?: string\) => void/);
  assert.match(queueSource, /onModifyRequest: \(notice\?: string\) => void/);
  assert.match(queueSource, /onClick=\{\(\) => onModifyRequest\(recoveryNotice \?\? undefined\)\}/);
});

test("a request-editing conflict makes the primary action recoverable instead of disabled", () => {
  const source = readFileSync(componentPath, "utf8");

  assert.match(source, /primaryAction\.kind === "modify_request"/);
  assert.match(source, /onCancel\(blockedConfirmationRecoveryNotice\(view\.confirmationItems\) \?\? undefined\)/);
  assert.match(source, /primaryAction\.kind === "blocked"/);
});

test("place search retains only same-query candidates after a recoverable retry", () => {
  const suggestions = {
    place_stable_id: "must:shancheng",
    query: "重庆 山城步道",
    options: [],
    recommended_provider_place_id: null,
    recommendation_reason: null,
  };

  assert.equal(shouldKeepPreviousPlaceSearchSuggestions(suggestions, " 重庆 山城步道 "), true);
  assert.equal(shouldKeepPreviousPlaceSearchSuggestions(suggestions, "重庆 洪崖洞"), false);
  assert.equal(shouldKeepPreviousPlaceSearchSuggestions(null, "重庆 山城步道"), false);
});

test("confirmation queue announces concise progress instead of its entire interactive form", () => {
  const queueSource = readFileSync(queuePath, "utf8");

  assert.match(queueSource, /role="status"/);
  assert.match(queueSource, /aria-atomic="true"/);
  assert.match(queueSource, /确认清单更新/);
  assert.doesNotMatch(queueSource, /<section className="uc-confirmation-workbench" aria-label="确认清单" aria-live="polite">/);
});

test("place confirmation presents a recommendation without silently confirming it", () => {
  const html = renderToStaticMarkup(
    <PrePlanConfirmationQueue
      items={[{
        id: "must-place:shancheng",
        kind: "must_place",
        title: "确认「山城步道」具体是哪一处",
        detail: "确认后才会使用真实的位置和路线数据。",
        identityId: "shancheng",
        tone: "todo",
      }]}
      confirmedItems={[]}
      identities={[{
        stable_id: "shancheng",
        original_name: "山城步道",
        canonical_name: null,
        city: "重庆",
        ownership: "must",
        fixed_event_id: null,
        resolution_status: "ambiguous",
        provider: null,
        provider_place_id: null,
        latitude: null,
        longitude: null,
        category: null,
        source_fragment_ids: ["direct"],
        confirmation_options: [{
          provider_place_id: "amap-shancheng",
          canonical_name: "山城步道（中兴路段）",
          address_summary: "重庆市渝中区中兴路",
          category: null,
          city: "重庆",
        }],
        resolution_confidence: null,
      }]}
      events={[]}
      questions={[]}
      busy={false}
      canGeneratePreview={false}
      onModifyRequest={() => undefined}
      onConfirmPlace={() => undefined}
      onSearchPlace={async () => ({ kind: "failed", message: "地点服务暂时不可用。", retryable: true })}
      onUpdateFixedLocation={() => undefined}
      renderClarification={() => null}
    />,
  );

  assert.match(html, /系统推荐/);
  assert.match(html, /山城步道（中兴路段）/);
  assert.match(html, /推荐依据：基于地点名称和本次目的地的提供商检索排序/);
  assert.match(html, /采用这个地点/);
  assert.match(html, /换一个 \/ 搜索地点/);
  assert.doesNotMatch(html, /已确认地点/);
});

test("place confirmation uses a plain search action when no provider candidate exists", () => {
  const html = renderToStaticMarkup(
    <PrePlanConfirmationQueue
      items={[{
        id: "must-place:shancheng",
        kind: "must_place",
        title: "确认「山城步道」具体是哪一处",
        detail: "确认后才会使用真实的位置和路线数据。",
        identityId: "shancheng",
        tone: "todo",
      }]}
      confirmedItems={[]}
      identities={[{
        stable_id: "shancheng",
        original_name: "山城步道",
        canonical_name: null,
        city: "重庆",
        ownership: "must",
        fixed_event_id: null,
        resolution_status: "ambiguous",
        provider: null,
        provider_place_id: null,
        latitude: null,
        longitude: null,
        category: null,
        source_fragment_ids: ["direct"],
        confirmation_options: [],
        resolution_confidence: null,
      }]}
      events={[]}
      questions={[]}
      busy={false}
      canGeneratePreview={false}
      onModifyRequest={() => undefined}
      onConfirmPlace={() => undefined}
      onSearchPlace={async () => ({ kind: "failed", message: "地点服务暂时不可用。", retryable: true })}
      onUpdateFixedLocation={() => undefined}
      renderClarification={() => null}
    />,
  );

  assert.match(html, /暂时没有可确认的地点候选/);
  assert.match(html, /<button[^>]*>搜索地点<\/button>/);
  assert.doesNotMatch(html, /换一个 \/ 搜索地点/);
});

test("confirmation queue expands only the first actionable place by default", () => {
  const identity = (stableId: string, placeId: string, address: string) => ({
    stable_id: stableId,
    original_name: stableId,
    canonical_name: null,
    city: "重庆",
    ownership: "must" as const,
    fixed_event_id: null,
    resolution_status: "ambiguous" as const,
    provider: null,
    provider_place_id: null,
    latitude: null,
    longitude: null,
    category: null,
    source_fragment_ids: ["direct"],
    confirmation_options: [{
      provider_place_id: placeId,
      canonical_name: `${stableId} 推荐地点`,
      address_summary: address,
      category: null,
      city: "重庆",
    }],
    resolution_confidence: null,
  });
  const html = renderToStaticMarkup(
    <PrePlanConfirmationQueue
      items={[
        { id: "conflict:dates", kind: "conflict", title: "抵达时间不能晚于离开时间", detail: "请先返回修改需求。", questionId: null, tone: "conflict" },
        { id: "must-place:hongyadong", kind: "must_place", title: "确认「洪崖洞」具体是哪一处", detail: "确认后才会使用真实的位置和路线数据。", identityId: "hongyadong", tone: "todo" },
        { id: "must-place:shancheng", kind: "must_place", title: "确认「山城步道」具体是哪一处", detail: "确认后才会使用真实的位置和路线数据。", identityId: "shancheng", tone: "todo" },
      ]}
      confirmedItems={[]}
      identities={[
        identity("hongyadong", "amap-hongyadong", "重庆市渝中区嘉陵江滨江路"),
        identity("shancheng", "amap-shancheng", "重庆市渝中区中兴路"),
      ]}
      events={[]}
      questions={[]}
      busy={false}
      canGeneratePreview={false}
      onModifyRequest={() => undefined}
      onConfirmPlace={() => undefined}
      onSearchPlace={async () => ({ kind: "failed", message: "地点服务暂时不可用。", retryable: true })}
      onUpdateFixedLocation={() => undefined}
      renderClarification={() => null}
    />,
  );

  assert.match(html, /抵达时间不能晚于离开时间/);
  assert.match(html, /重庆市渝中区嘉陵江滨江路/);
  assert.doesNotMatch(html, /重庆市渝中区中兴路/);
  assert.equal((html.match(/采用这个地点/g) ?? []).length, 1);
  assert.match(html, /选择地点/);
});

test("confirmation queue never calls a blocked zero-item Draft ready", () => {
  const html = renderToStaticMarkup(
    <PrePlanConfirmationQueue
      items={[]}
      confirmedItems={[]}
      identities={[]}
      events={[]}
      questions={[]}
      busy={false}
      canGeneratePreview={false}
      onModifyRequest={() => undefined}
      onConfirmPlace={() => undefined}
      onSearchPlace={async () => ({ kind: "failed", message: "地点服务暂时不可用。", retryable: true })}
      onUpdateFixedLocation={() => undefined}
      renderClarification={() => null}
    />,
  );

  assert.match(html, /请修改旅行信息/);
  assert.match(html, /目前没有可直接确认的项目/);
  assert.match(html, /<button[^>]*>修改旅行信息<\/button>/);
  assert.doesNotMatch(html, /关键信息已齐备/);
});

test("confirmation queue tells travelers to revise the request when no displayed blocker can be handled here", () => {
  const html = renderToStaticMarkup(
    <PrePlanConfirmationQueue
      items={[{
        id: "conflict:dates",
        kind: "conflict",
        title: "到达时间不能晚于离开时间",
        detail: "请调整到达或离开的时间后再继续。",
        questionId: null,
        tone: "conflict",
      }]}
      confirmedItems={[]}
      identities={[]}
      events={[]}
      questions={[]}
      busy={false}
      canGeneratePreview={false}
      onModifyRequest={() => undefined}
      onConfirmPlace={() => undefined}
      onSearchPlace={async () => ({ kind: "failed", message: "地点服务暂时不可用。", retryable: true })}
      onUpdateFixedLocation={() => undefined}
      renderClarification={() => null}
    />,
  );

  assert.match(html, /请修改旅行信息/);
  assert.match(html, /目前没有可直接确认的项目/);
  assert.doesNotMatch(html, /还需确认 1 项/);
});

test("pre-plan confirmation controls retain a visible keyboard focus ring", () => {
  const styles = readFileSync(stylesPath, "utf8");
  assert.match(styles, /\.uc-confirmation-item-action\s*\{[\s\S]*min-height:\s*44px/);
  assert.match(styles, /@media \(max-width: 760px\)\s*\{[\s\S]*\.uc-confirmation-item-action\s*\{[\s\S]*width:\s*100%/);
  assert.match(styles, /\.uc-confirmation-item-action:focus-visible/);
  assert.match(styles, /\.uc-intent-primary:focus-visible/);
  assert.match(styles, /\.uc-intent-secondary:focus-visible/);
  assert.match(styles, /\.uc-intent-text-action:focus-visible/);
  assert.match(styles, /\.uc-intent-choice button:focus-visible/);
  assert.match(styles, /\.uc-intent-editor input:focus-visible/);
  assert.match(styles, /\.uc-intent-clarification select:focus-visible/);
});

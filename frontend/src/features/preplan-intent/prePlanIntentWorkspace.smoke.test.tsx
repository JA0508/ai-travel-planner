import assert from "node:assert/strict";
import test from "node:test";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { PrePlanIntentWorkspace } from "./PrePlanIntentWorkspace";
import { PrePlanConfirmationQueue } from "./PrePlanConfirmationQueue";

const componentPath = fileURLToPath(new URL("./PrePlanIntentWorkspace.tsx", import.meta.url));
const queuePath = fileURLToPath(new URL("./PrePlanConfirmationQueue.tsx", import.meta.url));
const stylesPath = fileURLToPath(new URL("../../app/globals.css", import.meta.url));

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
  assert.match(source, /feedback\.action === "focus_place_confirmation"[\s\S]*requestPlaceConfirmationFocus\("must_place"\)/);
  assert.match(source, /placeFocusRequest=\{placeConfirmationFocusRequest \?\? undefined\}/);
  assert.match(queueSource, /placeFocusRequest/);
  assert.match(queueSource, /scrollIntoView/);
});

test("pre-plan preview can take a blocked fixed arrangement to its location confirmation", () => {
  const source = readFileSync(componentPath, "utf8");
  const queueSource = readFileSync(queuePath, "utf8");
  assert.match(source, /feedback\.action === "focus_fixed_place_confirmation"[\s\S]*requestPlaceConfirmationFocus\("fixed_place"\)/);
  assert.match(queueSource, /item\.kind === placeFocusRequest\.kind/);
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
  assert.match(queueSource, /没有找到「\$\{trimmed\}」对应的地点/);
  assert.match(queueSource, /补充城市、街区、附近地标或准确地址/);
  assert.doesNotMatch(source, /function FixedPlaceConfirmation/);
  assert.doesNotMatch(source, /function MustPlaceConfirmation/);
  assert.doesNotMatch(source, /function FixedArrangementSummary/);
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

  assert.match(html, /还需要检查需求/);
  assert.match(html, /当前没有可直接确认的项目/);
  assert.match(html, /<button[^>]*>修改原始需求<\/button>/);
  assert.doesNotMatch(html, /关键信息已齐备/);
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

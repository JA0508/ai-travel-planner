import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import { fileURLToPath } from "node:url";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";

import { SafeReplaceCandidates, SafeReplacePreview } from "./SafeReplaceExperience";
import type {
  SafeReplaceCandidate,
  SafeReplacePreviewModel,
} from "./safeReplaceModel";

const experiencePath = fileURLToPath(new URL("./SafeReplaceExperience.tsx", import.meta.url));
const previewPath = fileURLToPath(new URL("./ExecutableRoutePreview.tsx", import.meta.url));
const roadbookPath = fileURLToPath(new URL("./SavedLivingRoadbook.tsx", import.meta.url));

test("candidate stage presents a bounded field-note choice without exposing provider internals", () => {
  const html = renderToStaticMarkup(
    <SafeReplaceCandidates
      targetName="青芝坞餐厅"
      candidates={[candidate("茶人村", -240, true), candidate("远山宴", 7200, false)]}
      loading={false}
      onSelect={() => undefined}
      onKeep={() => undefined}
    />,
  );

  assert.match(html, /换一个更适合你的地点/);
  assert.match(html, /我们只替换这一站/);
  assert.match(html, /茶人村/);
  assert.match(html, /路上约少 4 分钟/);
  assert.match(html, /远山宴/);
  assert.match(html, /可能赶不上后面的固定安排/);
  assert.match(html, /看看换成这里/);
  assert.doesNotMatch(html, /provider_place_id|latitude|longitude|score|ranking/);
  assert.doesNotMatch(html, /换成这个地点/);
});

test("safe preview makes the bounded change, route evidence and protected items readable", () => {
  const html = renderToStaticMarkup(
    <SafeReplacePreview
      targetName="青芝坞餐厅"
      candidate={candidate("茶人村", -900, true)}
      model={previewModel}
      applying={false}
      onApply={() => undefined}
      onKeep={() => undefined}
      onOtherCandidates={() => undefined}
    />,
  );

  assert.match(html, /换成这里以后，这一段会这样走/);
  assert.match(html, /换之前/);
  assert.match(html, /换成茶人村以后/);
  assert.match(html, /灵隐寺/);
  assert.match(html, /青芝坞餐厅/);
  assert.match(html, /茶人村/);
  assert.match(html, /保持不变/);
  assert.match(html, /中国茶叶博物馆/);
  assert.match(html, /已经留好的时间，不会移动/);
  assert.match(html, /换成这个地点/);
  assert.match(html, /保持原地点/);
});

test("unsafe preview disables apply and says the saved route was not changed", () => {
  const html = renderToStaticMarkup(
    <SafeReplacePreview
      targetName="青芝坞餐厅"
      candidate={candidate("远山宴", 7200, false)}
      applying={false}
      onApply={() => undefined}
      onKeep={() => undefined}
      onOtherCandidates={() => undefined}
    />,
  );

  assert.match(html, /这个地点现在不太适合换进去/);
  assert.match(html, /你的原路线没有被改变/);
  assert.match(html, /disabled=""/);
  assert.match(html, /看看其他地点/);
});

test("saved flow reuses candidate, mutation proposal, apply and compensating undo APIs", () => {
  const source = [experiencePath, previewPath, roadbookPath]
    .map((path) => readFileSync(path, "utf8"))
    .join("\n");

  assert.match(source, /previewCompletionTaskCandidates/);
  assert.match(source, /previewPersistedMutation/);
  assert.match(source, /applyPersistedMutationProposal/);
  assert.match(source, /undoPersistedRevision/);
  assert.match(source, /buildSafeReplaceCommandEnvelope/);
  assert.match(source, /LatestReplaceRequest/);
  assert.match(source, /换一个/);
  assert.match(source, /刚刚换好/);
  assert.match(source, /这个地点是你明确保留的安排/);
  assert.match(source, /X-Idempotency-Key/);
  assert.doesNotMatch(source, /localStorage/);
  assert.doesNotMatch(source, /RecommendationEngine|ReplacementCoordinatorV2|SwapPlanner/);
});

const previewModel: SafeReplacePreviewModel = {
  change: { stopId: "stop-meal", beforeName: "青芝坞餐厅", afterName: "茶人村" },
  before: {
    item: item("青芝坞餐厅"),
    inbound: { fromName: "灵隐寺", toName: "青芝坞餐厅", distanceMeters: 900, durationSeconds: 900 },
    outbound: { fromName: "青芝坞餐厅", toName: "中国茶叶博物馆", distanceMeters: 1200, durationSeconds: 1200 },
  },
  after: {
    item: item("茶人村"),
    inbound: { fromName: "灵隐寺", toName: "茶人村", distanceMeters: 800, durationSeconds: 600 },
    outbound: { fromName: "茶人村", toName: "中国茶叶博物馆", distanceMeters: 800, durationSeconds: 600 },
  },
  protectedItems: [
    { id: "stop-must", name: "灵隐寺", reason: "你明确说想去" },
    { id: "stop-fixed", name: "中国茶叶博物馆", reason: "已经留好的时间，不会移动" },
  ],
};

function item(name: string) {
  return {
    stable_id: "stop-meal",
    name,
    type: "restaurant" as const,
    start_time: "11:00",
    end_time: "12:00",
    is_fixed: false,
  };
}

function candidate(name: string, deltaSeconds: number, safe: boolean): SafeReplaceCandidate {
  return {
    stable_id: `amap:${name}`,
    name,
    type: "restaurant",
    suggested_day: 1,
    suggested_block: "afternoon",
    reasoning_summary: safe ? "它仍适合当前时段，而且前后两段路程更短。" : "这个地点是真实候选，但可能赶不上后面的固定安排。",
    itinerary_relation_summary: "只替换这一站，并重新检查它前后的两段路线。",
    verified_place: {
      stable_id: `amap:${name}`,
      original_name: name,
      canonical_name: name,
      provider: "amap",
      provider_place_id: `provider:${name}`,
      latitude: 30.2,
      longitude: 120.1,
      category: "杭帮菜",
      source_fragment_ids: [],
    },
    route_impact: {
      safe_to_apply: safe,
      before_duration_s: 2100,
      after_duration_s: safe ? 1200 : 9300,
      delta_duration_s: deltaSeconds,
      inbound: safe ? { from_name: "灵隐寺", to_name: name, distance_m: 800, duration_s: 600, provider: "amap", data_status: "confirmed" } : null,
      outbound: safe ? { from_name: name, to_name: "中国茶叶博物馆", distance_m: 800, duration_s: 600, provider: "amap", data_status: "confirmed" } : null,
      blocking_reason: safe ? null : "fixed_event_at_risk",
    },
  };
}

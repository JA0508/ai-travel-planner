import assert from "node:assert/strict";
import test from "node:test";

import {
  LatestReplaceRequest,
  buildSafeReplaceCommandEnvelope,
  buildSafeReplacePreviewModel,
  formatSafeReplaceRouteDelta,
  isSafeReplaceEligible,
  parseSafeReplaceCandidates,
  safeReplaceFailureMessage,
  type SafeReplaceCandidate,
} from "./safeReplaceModel";
import type { RoutePreviewItinerary, RoutePreviewItem } from "./routePreviewModel";

test("only enables replace for a verified system-suggested flexible stop", () => {
  assert.equal(isSafeReplaceEligible(stop()), true);
  assert.equal(isSafeReplaceEligible(stop({ is_fixed: true })), false);
  assert.equal(isSafeReplaceEligible(stop({ source_label: "必去" })), false);
  assert.equal(isSafeReplaceEligible(stop({ source_type: "user_seed" })), false);
  assert.equal(isSafeReplaceEligible(stop({ canonical_place_id: null })), false);
  assert.equal(isSafeReplaceEligible(stop({ verified_place: null })), false);
});

test("builds a single existing replace_stop command from verified server candidate evidence", () => {
  const envelope = buildSafeReplaceCommandEnvelope("revision-1", stop(), candidate());

  assert.equal(envelope.base_revision_id, "revision-1");
  assert.equal(envelope.mutation_kind, "swap");
  assert.equal(envelope.commands.length, 1);
  assert.deepEqual(envelope.commands[0], {
    type: "replace_stop",
    stop_id: "stop-meal",
    replacement: {
      name: "茶人村",
      type: "restaurant",
      reasoning_summary: "它仍适合当前时段，而且前后两段路程更短。",
      itinerary_relation_summary: "只替换这一站，并重新检查它前后的两段路线。",
      verified_place: candidate().verified_place,
      route_impact: candidate().route_impact,
    },
  });
});

test("accepts only safe candidates without padding and keeps deterministic server order", () => {
  const current = candidate();
  current.verified_place.provider_place_id = "current-place";
  const unsafe = candidate();
  unsafe.verified_place.provider_place_id = "unsafe-place";
  unsafe.route_impact.safe_to_apply = false;
  unsafe.route_impact.blocking_reason = "fixed_event_at_risk";
  const unverified = structuredClone(candidate()) as unknown as Record<string, unknown>;
  delete (unverified.verified_place as Record<string, unknown>).provider_place_id;
  const first = candidate();
  const second = candidate();
  first.verified_place.provider_place_id = "candidate-1";
  second.verified_place.provider_place_id = "candidate-2";
  const duplicate = structuredClone(first);
  duplicate.name = "茶人村（龙井店）";
  const values: unknown[] = [current, second, unsafe, duplicate, first, unverified];

  const parsed = parseSafeReplaceCandidates(values, "current-place");

  assert.equal(parsed.length, 2);
  assert.deepEqual(parsed.map((entry) => entry.verified_place.provider_place_id), [
    "candidate-2",
    "candidate-1",
  ]);
  assert.equal(parsed.every((entry) => entry.route_impact.safe_to_apply), true);
});

test("derives one changed slot and protected items only from authoritative snapshots", () => {
  const before = itinerary("青芝坞餐厅", 900, 1200);
  const after = itinerary("茶人村", 600, 600);
  const model = buildSafeReplacePreviewModel(before, after, "stop-meal");

  assert.deepEqual(model.change, {
    stopId: "stop-meal",
    beforeName: "青芝坞餐厅",
    afterName: "茶人村",
  });
  assert.equal(model.before.inbound?.durationSeconds, 900);
  assert.equal(model.before.outbound?.durationSeconds, 1200);
  assert.equal(model.after.inbound?.durationSeconds, 600);
  assert.equal(model.after.outbound?.durationSeconds, 600);
  assert.deepEqual(
    model.protectedItems.map((item) => [item.name, item.reason]),
    [
      ["灵隐寺", "你明确说想去"],
      ["中国茶叶博物馆", "已经留好的时间，不会移动"],
    ],
  );

  const changedFixed = structuredClone(after);
  changedFixed.days[0].blocks[0].items[2].start_time = "15:00";
  assert.deepEqual(
    buildSafeReplacePreviewModel(before, changedFixed, "stop-meal").protectedItems.map((item) => item.name),
    ["灵隐寺"],
  );
});

test("never renders missing route evidence as zero", () => {
  const after = itinerary("茶人村", null, null);
  const model = buildSafeReplacePreviewModel(itinerary("青芝坞餐厅", 900, 1200), after, "stop-meal");

  assert.equal(model.after.inbound, null);
  assert.equal(model.after.outbound, null);
  assert.equal(formatSafeReplaceRouteDelta(null), "路程变化待确认");
  assert.doesNotMatch(JSON.stringify(model.after), /"durationSeconds":0/);
});

test("slow candidate preview cannot replace the latest selection", () => {
  const requests = new LatestReplaceRequest();
  const first = requests.begin();
  const second = requests.begin();

  assert.equal(requests.isLatest(first), false);
  assert.equal(requests.isLatest(second), true);
  requests.cancel();
  assert.equal(requests.isLatest(second), false);
});

test("translates stale, failed and unsafe operations without protocol codes", () => {
  const stale = safeReplaceFailureMessage("stale_mutation_proposal", "preview");
  const failed = safeReplaceFailureMessage(undefined, "apply");
  const unsafe = safeReplaceFailureMessage("replacement_breaks_fixed_event", "preview");
  const nestedUnsafe = safeReplaceFailureMessage(
    "mutation_command_failed",
    "preview",
    { reason_code: "replacement_breaks_fixed_event" },
  );

  assert.match(stale, /路线刚刚发生了变化/);
  assert.match(failed, /原来的地点仍然保留/);
  assert.match(unsafe, /固定安排/);
  assert.match(nestedUnsafe, /固定安排/);
  assert.doesNotMatch(`${stale}${failed}${unsafe}${nestedUnsafe}`, /409|422|stale_|replacement_/);
});

function candidate(): SafeReplaceCandidate {
  return {
    stable_id: "amap:tea-village",
    name: "茶人村",
    type: "restaurant",
    suggested_day: 1,
    suggested_block: "afternoon",
    reasoning_summary: "它仍适合当前时段，而且前后两段路程更短。",
    itinerary_relation_summary: "只替换这一站，并重新检查它前后的两段路线。",
    verified_place: {
      stable_id: "amap:tea-village",
      original_name: "茶人村",
      canonical_name: "茶人村",
      provider: "amap",
      provider_place_id: "tea-village",
      latitude: 30.229,
      longitude: 120.111,
      category: "杭帮菜",
      source_fragment_ids: [],
    },
    route_impact: {
      safe_to_apply: true,
      before_duration_s: 2100,
      after_duration_s: 1200,
      delta_duration_s: -900,
      inbound: {
        from_name: "灵隐寺",
        to_name: "茶人村",
        distance_m: 800,
        duration_s: 600,
        provider: "amap",
        data_status: "confirmed",
      },
      outbound: {
        from_name: "茶人村",
        to_name: "中国茶叶博物馆",
        distance_m: 800,
        duration_s: 600,
        provider: "amap",
        data_status: "confirmed",
      },
      blocking_reason: null,
    },
  };
}

function itinerary(mealName: string, inboundSeconds: number | null, outboundSeconds: number | null): RoutePreviewItinerary {
  return {
    trip_days: 1,
    planning_anchor_source: { source_type: "provided_hotel", source_name: "西湖边酒店" },
    days: [{
      day: 1,
      blocks: [{
        block_type: "afternoon",
        start_time: "09:00",
        end_time: "17:00",
        items: [
          stop({
            stable_id: "stop-must",
            name: "灵隐寺",
            source_type: "user_seed",
            source_label: "必去",
            start_time: "09:00",
            end_time: "10:30",
          }),
          stop({
            name: mealName,
            travel_from_name: "灵隐寺",
            travel_duration_s: inboundSeconds,
          }),
          stop({
            stable_id: "stop-fixed",
            name: "中国茶叶博物馆",
            source_type: "user_fixed",
            source_label: "固定安排",
            is_fixed: true,
            start_time: "14:00",
            end_time: "16:00",
            travel_from_name: mealName,
            travel_duration_s: outboundSeconds,
          }),
        ],
      }],
    }],
  };
}

function stop(overrides: Partial<RoutePreviewItem> = {}): RoutePreviewItem {
  return {
    stable_id: "stop-meal",
    name: "青芝坞餐厅",
    type: "restaurant",
    city: "杭州",
    latitude: 30.26049,
    longitude: 120.12745,
    start_time: "11:00",
    end_time: "12:00",
    is_fixed: false,
    source_type: "auto_seeded_meal",
    source_label: "系统补充",
    canonical_place_id: "qingzhiwu",
    verified_place: {
      stable_id: "amap:qingzhiwu",
      original_name: "青芝坞餐厅",
      canonical_name: "青芝坞餐厅",
      provider: "amap",
      provider_place_id: "qingzhiwu",
      latitude: 30.26049,
      longitude: 120.12745,
      category: "中餐厅",
      source_fragment_ids: [],
    },
    travel_from_name: "灵隐寺",
    travel_distance_m: 900,
    travel_duration_s: 900,
    travel_data_status: "confirmed",
    ...overrides,
  };
}

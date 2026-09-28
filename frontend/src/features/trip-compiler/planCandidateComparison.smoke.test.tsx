import assert from "node:assert/strict";
import test from "node:test";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";

import { PlanCandidateComparison, type PlanCandidateResponse } from "./PlanCandidateComparison";

const response: PlanCandidateResponse = {
  intent_digest: "intent-digest",
  planning_run_id: "run-1",
  status: "generated",
  expires_at: "2026-08-13T00:00:00Z",
  comparison: [{ candidate_id: "route-1", highlights: ["保留更多午后空白", "固定安排前后不赶"] }],
  candidates: [{
    id: "route-1",
    candidate_hash: "candidate-hash",
    strategy: "relaxed",
    title: "慢一点看杭州",
    tradeoff_summary: "少排一个地点，换来更完整的湖边时间。",
    metrics: {
      fixed_coverage: 1,
      must_coverage: 2,
      optional_coverage: 1,
      total_travel_minutes: 42,
      activity_minutes: 360,
      max_daily_activity_minutes: 240,
      free_buffer_minutes: 150,
      missing_travel_data: false,
      minimum_daily_slack_minutes: 75,
      rushed_day_count: 0,
      infeasible_day_count: 0,
      risk_count: 0,
      travel_data_completeness: "complete",
      daily_windows: [],
    },
    itinerary: {
      trip_days: 1,
      days: [{ day: 1, blocks: [{ block_type: "morning", start_time: "09:00", end_time: "12:00", items: [{
        stable_id: "west-lake",
        name: "西湖",
        type: "scenic",
        start_time: "09:00",
        end_time: "11:00",
        duration_minutes: 120,
        is_fixed: true,
        travel_from_name: "杭州东站",
        travel_duration_s: 1800,
        travel_distance_m: 6200,
        travel_data_status: "confirmed",
      }] }] }],
    },
  }],
};

test("candidate selection renders a route directory and one complete journey", () => {
  const html = renderToStaticMarkup(<PlanCandidateComparison response={response} selectedId="route-1" busy={false} error={null} onSelect={() => undefined} onConfirm={() => undefined} onBack={() => undefined} />);
  assert.match(html, /路线怎么不同/);
  assert.match(html, /aria-label="路线方案目录"/);
  assert.match(html, /慢一点看杭州/);
  assert.match(html, /固定安排已保护/);
  assert.match(html, /路程已确认/);
  assert.match(html, /为什么选这条路/);
  assert.doesNotMatch(html, /Planning Run/);
  assert.doesNotMatch(html, /candidate_hash/);
});

test("candidate selection keeps missing travel totals visibly unknown", () => {
  const missingTravel = structuredClone(response);
  missingTravel.candidates[0].metrics.total_travel_minutes = null;
  const html = renderToStaticMarkup(<PlanCandidateComparison response={missingTravel} selectedId="route-1" busy={false} error={null} onSelect={() => undefined} onConfirm={() => undefined} onBack={() => undefined} />);
  assert.match(html, /路上时间<\/dt><dd>待确认/);
  assert.doesNotMatch(html, /null 分钟/);
  assert.doesNotMatch(html, /undefined 分钟/);
});

test("candidate selection does not call missing route evidence partially confirmed", () => {
  const missingTravel = structuredClone(response);
  missingTravel.candidates[0].metrics.travel_data_completeness = "missing";
  missingTravel.candidates[0].metrics.missing_travel_data = true;
  missingTravel.candidates[0].metrics.total_travel_minutes = null;

  const html = renderToStaticMarkup(<PlanCandidateComparison response={missingTravel} selectedId="route-1" busy={false} error={null} onSelect={() => undefined} onConfirm={() => undefined} onBack={() => undefined} />);

  assert.match(html, /路程待确认/);
  assert.doesNotMatch(html, /部分路程待确认/);
});

test("candidate selection keeps daily slack unknown when route data is incomplete", () => {
  const partialTravel = structuredClone(response);
  partialTravel.candidates[0].metrics.travel_data_completeness = "partial";
  partialTravel.candidates[0].metrics.missing_travel_data = true;

  const html = renderToStaticMarkup(<PlanCandidateComparison response={partialTravel} selectedId="route-1" busy={false} error={null} onSelect={() => undefined} onConfirm={() => undefined} onBack={() => undefined} />);

  assert.match(html, /每天至少留白<\/dt><dd>待确认/);
  assert.doesNotMatch(html, /每天至少留白<\/dt><dd>1 小时 15 分钟/);
});

test("candidate selection does not market incomplete route data as extra slack", () => {
  const incompleteRelaxed = structuredClone(response);
  incompleteRelaxed.candidates[0].strategy = "relaxed";
  incompleteRelaxed.candidates[0].title = "留出更多空白";
  incompleteRelaxed.candidates[0].tradeoff_summary = "最少每天预留 75 分钟弹性时间。";
  incompleteRelaxed.candidates[0].metrics.travel_data_completeness = "partial";
  incompleteRelaxed.candidates[0].metrics.missing_travel_data = true;

  const html = renderToStaticMarkup(<PlanCandidateComparison response={incompleteRelaxed} selectedId="route-1" busy={false} error={null} onSelect={() => undefined} onConfirm={() => undefined} onBack={() => undefined} />);

  assert.match(html, /路线方案/);
  assert.match(html, /路程仍待确认/);
  assert.doesNotMatch(html, /留白更多/);
  assert.doesNotMatch(html, /最少每天预留 75 分钟弹性时间。/);
});

test("candidate selection does not present its internal route center as a confirmed leg", () => {
  const anchoredAtRouteCenter = structuredClone(response);
  anchoredAtRouteCenter.candidates[0].itinerary.planning_anchor_source = {
    source_type: "route_centroid",
    source_name: "西湖附近路线中心",
  };
  anchoredAtRouteCenter.candidates[0].itinerary.days[0].blocks[0].items[0] = {
    ...anchoredAtRouteCenter.candidates[0].itinerary.days[0].blocks[0].items[0],
    travel_from_name: "西湖附近路线中心",
    travel_duration_s: 0,
    travel_distance_m: 1,
  };

  const html = renderToStaticMarkup(<PlanCandidateComparison response={anchoredAtRouteCenter} selectedId="route-1" busy={false} error={null} onSelect={() => undefined} onConfirm={() => undefined} onBack={() => undefined} />);

  assert.doesNotMatch(html, /西湖附近路线中心/);
  assert.doesNotMatch(html, /0 分钟 · 1 米/);
});

test("candidate selection shows the deterministic reason for a system-supplemented stop", () => {
  const supplemented = structuredClone(response);
  supplemented.candidates[0].itinerary.days[0].blocks[0].items[0] = {
    ...supplemented.candidates[0].itinerary.days[0].blocks[0].items[0],
    is_fixed: false,
    source_type: "auto_seeded_meal",
    source_label: "系统补充",
    source_reason: "系统为这一天补上的午饭，避开了下午的固定安排。",
  };

  const html = renderToStaticMarkup(<PlanCandidateComparison response={supplemented} selectedId="route-1" busy={false} error={null} onSelect={() => undefined} onConfirm={() => undefined} onBack={() => undefined} />);

  assert.match(html, /为什么补入/);
  assert.match(html, /系统为这一天补上的午饭，避开了下午的固定安排。/);
});

test("candidate selection does not invent a reason when a system-supplemented stop lacks evidence", () => {
  const supplemented = structuredClone(response);
  supplemented.candidates[0].itinerary.days[0].blocks[0].items[0] = {
    ...supplemented.candidates[0].itinerary.days[0].blocks[0].items[0],
    is_fixed: false,
    source_type: "auto_seeded_poi",
    source_label: "系统补充",
    source_reason: null,
    placement_reason: null,
  };

  const html = renderToStaticMarkup(<PlanCandidateComparison response={supplemented} selectedId="route-1" busy={false} error={null} onSelect={() => undefined} onConfirm={() => undefined} onBack={() => undefined} />);

  assert.doesNotMatch(html, /为什么补入/);
});

test("candidate meal rhythm copy only names applicable meal roles", () => {
  const lunchOnly = structuredClone(response);
  lunchOnly.candidates[0].itinerary.meal_rhythm = {
    policy_version: "meal-rhythm-v1",
    days: [{
      day: 1,
      slots: [
        {
          role: "lunch",
          status: "covered",
          window_start: "11:30",
          window_end: "14:00",
          explanation: "现有午饭已覆盖。",
        },
        {
          role: "dinner",
          status: "not_applicable",
          window_start: "17:30",
          window_end: "20:30",
          explanation: "当天行程已经结束。",
        },
      ],
      field_notes: [],
    }],
  };

  const html = renderToStaticMarkup(<PlanCandidateComparison response={lunchOnly} selectedId="route-1" busy={false} error={null} onSelect={() => undefined} onConfirm={() => undefined} onBack={() => undefined} />);

  assert.match(html, /午饭已安排/);
  assert.doesNotMatch(html, /午饭和晚饭已按适用时段安排/);
});

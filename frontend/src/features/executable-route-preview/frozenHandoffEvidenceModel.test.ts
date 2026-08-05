import assert from "node:assert/strict";
import test from "node:test";
import { buildFrozenHandoffEvidenceView } from "./frozenHandoffEvidenceModel";

test("saved frozen handoff evidence identifies its intent, readiness, trace, and fact boundaries", () => {
  const view = buildFrozenHandoffEvidenceView({
    status: "applied",
    can_apply: false,
    intent_revision_id: "intent_1",
    current_intent_revision_id: "intent_1",
    base_trip_revision_id: null,
    current_trip_revision_id: "revision_1",
    readiness_status: "ready_for_planning",
    blocking_reason_codes: [],
    warning_codes: ["route_data_missing"],
    trace: {
      decision_count: 4,
      accepted_decision_count: 3,
      rejected_decision_count: 1,
      warning_count: 1,
      reason_codes: [],
    },
  });

  assert.match(view.title, /已保存的规划依据/);
  assert.match(view.intentLabel, /intent_1/);
  assert.match(view.statusLabel, /已生成正式行程/);
  assert.match(view.readinessLabel, /可以开始规划/);
  assert.match(view.traceLabel, /4 项/);
  assert.match(view.heuristicBoundary, /系统判断/);
  assert.match(view.providerBoundary, /没有独立 provider evidence/);
});

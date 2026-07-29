import assert from "node:assert/strict";
import test from "node:test";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { fixtureForScenario, productResetFixtures } from "./productResetFixture";
import { applyFixtureRepair, findFixedEvent, findTravelLeg } from "./productResetModel";

const componentPath = fileURLToPath(new URL("./ProductResetPrototype.tsx", import.meta.url));

test("product-reset fixtures are explicit, typed local prototype data", () => {
  assert.equal(productResetFixtures.length, 3);
  for (const fixture of productResetFixtures) {
    assert.equal(fixture.draft.dataSource, "prototype_fixture");
    assert.equal(fixture.route.dataSource, "prototype_fixture");
    assert.ok(fixture.route.days.length >= 2);
  }
});

test("Shanghai fixture exposes the protected museum appointment", () => {
  const fixture = fixtureForScenario("shanghai");
  const museumActivity = fixture.route.days[1].activities.find((activity) => activity.title === "上海博物馆");
  assert.ok(museumActivity);
  const event = findFixedEvent(fixture.route, museumActivity);
  assert.equal(event?.startTime, "14:00");
  assert.equal(event?.endTime, "16:00");
  assert.equal(event?.protectedLabel, "已预约 · 不可随意移动");
});

test("rushed-day repair moves only the system suggestion and preserves must and fixed activities", () => {
  const fixture = fixtureForScenario("rushed");
  const proposal = fixture.repair;
  assert.ok(proposal);
  const beforeDayOne = fixture.route.days[0];
  assert.equal(beforeDayOne.activities.length, 5);
  assert.equal(beforeDayOne.load.travelMinutes, 95);
  assert.ok(findTravelLeg(beforeDayOne, "xa-lunch"));

  const after = applyFixtureRepair(fixture.route, proposal);
  const afterDayOne = after.days[0];
  const afterDayTwo = after.days[1];
  assert.equal(afterDayOne.activities.some((activity) => activity.id === proposal.movedActivityId), false);
  assert.equal(afterDayTwo.activities.some((activity) => activity.id === proposal.movedActivityId), true);
  assert.equal(afterDayOne.activities.some((activity) => activity.id === "xa-terracotta"), true);
  assert.equal(afterDayOne.activities.some((activity) => activity.id === "xa-wall"), true);
  assert.equal(afterDayOne.activities.some((activity) => activity.id === "xa-night"), true);
  assert.equal(afterDayOne.load.label, "刚好");
  assert.equal(after.risks.length, 0);
});

test("prototype component keeps the initial surface plain-language and local-only", () => {
  const source = readFileSync(componentPath, "utf8");
  assert.match(source, /这趟旅行/);
  assert.match(source, /看看我理解得对不对/);
  assert.doesNotMatch(source, /revision id/i);
  assert.doesNotMatch(source, /trace digest/i);
  assert.doesNotMatch(source, /planner_run_id/i);
  assert.doesNotMatch(source, /fetch\(/);
  assert.doesNotMatch(source, /postTripJson/);
  assert.doesNotMatch(source, /getTripJson/);
});

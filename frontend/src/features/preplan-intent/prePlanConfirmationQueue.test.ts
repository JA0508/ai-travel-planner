import assert from "node:assert/strict";
import test from "node:test";

import type { FixedEventIntent } from "@/features/intent-confirmation/intentTypes";
import { centeredConfirmationScrollTop, findPlaceFocusItem } from "./PrePlanConfirmationQueue";

test("centers a requested confirmation item within the current page scroll", () => {
  assert.equal(
    centeredConfirmationScrollTop({ top: 160, height: 160 }, 240, 800),
    80,
  );
});

test("never requests a negative confirmation scroll position", () => {
  assert.equal(
    centeredConfirmationScrollTop({ top: 20, height: 160 }, 0, 800),
    0,
  );
});

test("does not redirect a specific place recovery to a different confirmation item", () => {
  const items = [
    {
      id: "must-place:hongyadong",
      kind: "must_place" as const,
      title: "确认洪崖洞",
      detail: "确认后才会安排路线。",
      identityId: "must:hongyadong",
      tone: "todo" as const,
    },
  ];

  assert.equal(
    findPlaceFocusItem(items, { requestId: 1, kind: "must_place", stableId: "must:shancheng" }, []),
    null,
  );
});

test("uses the first same-kind confirmation item only when the recovery did not name a specific item", () => {
  const items = [
    {
      id: "must-place:hongyadong",
      kind: "must_place" as const,
      title: "确认洪崖洞",
      detail: "确认后才会安排路线。",
      identityId: "must:hongyadong",
      tone: "todo" as const,
    },
  ];

  assert.equal(
    findPlaceFocusItem(items, { requestId: 1, kind: "must_place" }, []),
    items[0],
  );
});

test("does not redirect a specific fixed-arrangement recovery to another arrangement", () => {
  const items = [
    {
      id: "fixed-place:hotel",
      kind: "fixed_place" as const,
      title: "确认酒店",
      detail: "确认后才会安排路线。",
      eventId: "event:hotel",
      identityId: null,
      tone: "todo" as const,
    },
  ];
  const events = [{
    event_id: "event:hotel",
    metadata: { field_id: "fixed:hotel" },
  }] as FixedEventIntent[];

  assert.equal(
    findPlaceFocusItem(items, { requestId: 1, kind: "fixed_place", fieldId: "fixed:airport" }, events),
    null,
  );
});

import assert from "node:assert/strict";
import test from "node:test";

import {
  buildRouteEditCommandEnvelope,
  buildSwapReplaceCommandEnvelope,
} from "./routeWorkspaceMutationCommands.ts";
import { buildEditableRouteDays } from "./routeWorkspaceEditModel.ts";

test("builds a route edit reorder command from stable scheduled item ids", () => {
  const itinerary = fixtureItinerary();
  const [day] = buildEditableRouteDays(itinerary);
  const editedDays = [
    {
      ...day,
      stops: [day.stops[1], day.stops[0], day.stops[2]],
    },
  ];

  const envelope = buildRouteEditCommandEnvelope(itinerary, "rev_1", editedDays);

  assert.deepEqual(envelope, {
    schema_version: "1.0",
    base_revision_id: "rev_1",
    mutation_kind: "route_edit",
    commands: [
      {
        type: "reorder_day",
        day: 1,
        ordered_stop_ids: ["stop_yu", "stop_museum", "stop_bund"],
      },
    ],
  });
});

test("does not build route edit commands for manual unplanned stops", () => {
  const itinerary = fixtureItinerary();
  const [day] = buildEditableRouteDays(itinerary);

  const envelope = buildRouteEditCommandEnvelope(itinerary, "rev_1", [day], [day.stops[0]]);

  assert.equal(envelope, null);
});

test("does not build route edit commands when scheduled item ids are missing", () => {
  const itinerary = fixtureItinerary();
  itinerary.days[0].blocks[0].items[0].stable_id = null;
  const [day] = buildEditableRouteDays(itinerary);

  const envelope = buildRouteEditCommandEnvelope(itinerary, "rev_1", [day]);

  assert.equal(envelope, null);
});

test("builds a swap replacement command from a stable target id", () => {
  const envelope = buildSwapReplaceCommandEnvelope(
    "rev_1",
    { stable_id: "stop_museum" },
    {
      name: "田子坊",
      type: "scenic",
      reasoning_summary: "更适合轻松街区体验。",
      itinerary_relation_summary: "保留上午 slot。",
    },
  );

  assert.deepEqual(envelope, {
    schema_version: "1.0",
    base_revision_id: "rev_1",
    mutation_kind: "swap",
    commands: [
      {
        type: "replace_stop",
        stop_id: "stop_museum",
        replacement: {
          name: "田子坊",
          type: "scenic",
          reasoning_summary: "更适合轻松街区体验。",
          itinerary_relation_summary: "保留上午 slot。",
        },
      },
    ],
  });
});

function fixtureItinerary() {
  return {
    planning_anchor_source: {
      source_type: "city",
      source_name: "上海",
    },
    days: [
      {
        day: 1,
        blocks: [
          {
            block_type: "morning" as const,
            start_time: "09:00:00",
            end_time: "12:00:00",
            items: [
              item("stop_museum", "上海博物馆", "09:00:00", "10:30:00"),
              item("stop_yu", "豫园", "10:45:00", "12:00:00"),
            ],
          },
          {
            block_type: "afternoon" as const,
            start_time: "14:00:00",
            end_time: "18:00:00",
            items: [item("stop_bund", "外滩", "14:30:00", "16:00:00")],
          },
        ],
      },
    ],
  };
}

function item(stableId: string | null, name: string, start: string, end: string) {
  return {
    stable_id: stableId,
    name,
    type: "scenic" as const,
    start_time: start,
    end_time: end,
    is_fixed: false,
    placement_reason: null,
    travel_from_name: null,
    travel_distance_m: null,
    travel_duration_s: null,
  };
}

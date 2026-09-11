import assert from "node:assert/strict";
import test from "node:test";

import {
  initialRouteWorkspaceUiState,
  reduceRouteWorkspaceUiState,
} from "./routeWorkspaceUiState.ts";

test("route workspace UI reducer toggles edit mode without changing active sheet", () => {
  const withSheet = reduceRouteWorkspaceUiState(initialRouteWorkspaceUiState, {
    type: "set_active_sheet",
    sheet: "completion",
  });
  const editing = reduceRouteWorkspaceUiState(withSheet, { type: "toggle_editing" });

  assert.equal(editing.editing, true);
  assert.equal(editing.activeSheet, "completion");
});

test("route workspace UI reducer can close editing from container callbacks", () => {
  const editing = reduceRouteWorkspaceUiState(initialRouteWorkspaceUiState, {
    type: "set_editing",
    editing: true,
  });
  const closed = reduceRouteWorkspaceUiState(editing, {
    type: "set_editing",
    editing: false,
  });

  assert.deepEqual(closed, initialRouteWorkspaceUiState);
});

test("route workspace UI reducer keeps sheet state isolated from edit state", () => {
  const editing = reduceRouteWorkspaceUiState(initialRouteWorkspaceUiState, {
    type: "set_editing",
    editing: true,
  });
  const withSheet = reduceRouteWorkspaceUiState(editing, {
    type: "set_active_sheet",
    sheet: "adjust",
  });
  const withoutSheet = reduceRouteWorkspaceUiState(withSheet, { type: "close_active_sheet" });

  assert.equal(withoutSheet.editing, true);
  assert.equal(withoutSheet.activeSheet, null);
});

test("route workspace focus requests preserve the current editing and sheet state", () => {
  const withSheet = reduceRouteWorkspaceUiState(initialRouteWorkspaceUiState, {
    type: "set_active_sheet",
    sheet: "completion",
  });
  const focused = reduceRouteWorkspaceUiState(withSheet, {
    type: "focus_day",
    day: 3,
  });

  assert.equal(focused.activeSheet, "completion");
  assert.equal(focused.editing, false);
  assert.deepEqual(focused.focusRequest, { day: 3, requestId: 1 });
});

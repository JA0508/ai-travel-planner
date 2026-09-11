import { useReducer } from "react";
import type { RouteWorkspaceSheetKey } from "@/components/trip/RouteWorkspaceShell";

export type RouteWorkspaceUiState = {
  editing: boolean;
  activeSheet: RouteWorkspaceSheetKey | null;
  focusRequest: { day: number; requestId: number } | null;
};

export type RouteWorkspaceUiAction =
  | { type: "toggle_editing" }
  | { type: "set_editing"; editing: boolean }
  | { type: "set_active_sheet"; sheet: RouteWorkspaceSheetKey | null }
  | { type: "focus_day"; day: number }
  | { type: "close_active_sheet" };

export const initialRouteWorkspaceUiState: RouteWorkspaceUiState = {
  editing: false,
  activeSheet: null,
  focusRequest: null,
};

export function reduceRouteWorkspaceUiState(
  state: RouteWorkspaceUiState,
  action: RouteWorkspaceUiAction,
): RouteWorkspaceUiState {
  if (action.type === "toggle_editing") {
    return {
      ...state,
      editing: !state.editing,
    };
  }

  if (action.type === "set_editing") {
    return {
      ...state,
      editing: action.editing,
    };
  }

  if (action.type === "set_active_sheet") {
    return {
      ...state,
      activeSheet: action.sheet,
    };
  }

  if (action.type === "focus_day") {
    return {
      ...state,
      focusRequest: {
        day: action.day,
        requestId: (state.focusRequest?.requestId ?? 0) + 1,
      },
    };
  }

  return {
    ...state,
    activeSheet: null,
  };
}

export function useRouteWorkspaceUiState(
  initialState: RouteWorkspaceUiState = initialRouteWorkspaceUiState,
) {
  const [state, dispatch] = useReducer(reduceRouteWorkspaceUiState, initialState);

  return {
    routeEditMode: state.editing,
    activeRouteSheet: state.activeSheet,
    toggleRouteEditMode: () => dispatch({ type: "toggle_editing" }),
    setRouteEditMode: (editing: boolean) => dispatch({ type: "set_editing", editing }),
    setActiveRouteSheet: (sheet: RouteWorkspaceSheetKey | null) =>
      dispatch({ type: "set_active_sheet", sheet }),
    focusRouteDay: (day: number) => dispatch({ type: "focus_day", day }),
    closeActiveRouteSheet: () => dispatch({ type: "close_active_sheet" }),
    routeFocusRequest: state.focusRequest,
  };
}

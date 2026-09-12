import type {
  ItineraryLike,
  RouteWorkspaceOverview,
} from "@/components/trip/MobileEditRouteWorkspace";
import type { RouteWorkspaceSheetKey } from "@/components/trip/RouteWorkspaceShell";

type RouteWorkspacePlannerRealism = {
  status?: "executable" | "needs_repair" | "unstable" | string | null;
  headline?: string | null;
} | null;

type RouteWorkspaceCompletionIntelligence = {
  trip_completeness?: number | null;
  action_tasks?: unknown[] | null;
} | null;

type RouteWorkspaceStayRecommendation = {
  options?: Array<{
    suggested_area_label?: string | null;
  }> | null;
} | null;

type RouteWorkspaceDepartureRecommendation = {
  options?: Array<{
    suggested_departure_label?: string | null;
  }> | null;
} | null;

export type RouteWorkspaceItinerary = ItineraryLike & {
  trip_days: number;
  planner_realism?: RouteWorkspacePlannerRealism;
  completion_intelligence?: RouteWorkspaceCompletionIntelligence;
  stay_recommendation?: RouteWorkspaceStayRecommendation;
  departure_recommendation?: RouteWorkspaceDepartureRecommendation;
};

export type RouteWorkspaceContainerViewModelInput = {
  city: string;
  itinerary: RouteWorkspaceItinerary;
  editing: boolean;
  activeSheet: RouteWorkspaceSheetKey | null;
  autoFilledCount: number;
  intentLine?: string | null;
  executionLine?: string | null;
  weakestDay?: RouteWorkspaceOverview["weakestDay"];
};

export type RouteWorkspaceShellViewModel = {
  city: string;
  tripDays: number;
  statusLabel: string;
  statusTone: "stable" | "attention";
  subtitle: string;
  completionAction: {
    headerLabel: string;
    label: string;
    hint: string;
  };
  completionPriority: "primary" | "secondary";
  primaryRouteFocus?: {
    day: number;
    label: string;
  };
  sheetTitle?: string;
  sheetDescription?: string;
};

export type RouteWorkspaceContainerViewModel = {
  shell: RouteWorkspaceShellViewModel;
  overview: RouteWorkspaceOverview;
};

export function buildRouteWorkspaceContainerViewModel({
  city,
  itinerary,
  editing,
  activeSheet,
  autoFilledCount,
  intentLine,
  executionLine,
  weakestDay,
}: RouteWorkspaceContainerViewModelInput): RouteWorkspaceContainerViewModel {
  return {
    shell: buildRouteWorkspaceShellViewModel({
      city,
      itinerary,
      editing,
      activeSheet,
      weakestDay,
    }),
    overview: buildRouteWorkspaceOverview({
      itinerary,
      autoFilledCount,
      intentLine,
      executionLine,
      weakestDay,
    }),
  };
}

export function buildRouteWorkspaceShellViewModel({
  city,
  itinerary,
  editing,
  activeSheet,
  weakestDay,
}: Pick<RouteWorkspaceContainerViewModelInput, "city" | "itinerary" | "editing" | "activeSheet" | "weakestDay">): RouteWorkspaceShellViewModel {
  const status = itinerary.planner_realism?.status;
  const hasCompletionTasks = (itinerary.completion_intelligence?.action_tasks?.length ?? 0) > 0;
  const hasRouteRisk = status === "needs_repair";
  const sheetCopy = buildRouteWorkspaceSheetCopy(activeSheet, hasCompletionTasks, hasRouteRisk);

  return {
    city,
    tripDays: itinerary.trip_days,
    statusLabel:
      status === "executable"
        ? "骨架可走"
        : hasRouteRisk
          ? "先看风险"
        : status === "unstable"
          ? "需要重排"
          : "还有空缺",
    statusTone: status === "executable" ? "stable" : "attention",
    subtitle: hasRouteRisk
      ? "先确认路线风险，再拖动、锁定、删除或补全其他信息。"
      : editing
        ? "拖动、锁定、删除或先放进待规划，完成后这版会成为当前计划。"
        : "先顺着路线看一遍。想改顺序、删点或继续补全时，再进入编辑。",
    completionAction: hasCompletionTasks
      ? hasRouteRisk
        ? { headerLabel: "其他补全", label: "补全", hint: "其他项" }
        : { headerLabel: "修复空缺", label: "补全", hint: "修空缺" }
      : { headerLabel: "检查路线", label: "检查", hint: "路线" },
    completionPriority: hasRouteRisk ? "secondary" : "primary",
    primaryRouteFocus:
      hasRouteRisk && weakestDay
        ? { day: weakestDay.day, label: `查看第 ${weakestDay.day} 天风险` }
        : undefined,
    sheetTitle: sheetCopy.title,
    sheetDescription: sheetCopy.description,
  };
}

export function buildRouteWorkspaceOverview({
  itinerary,
  autoFilledCount,
  intentLine,
  executionLine,
  weakestDay,
}: Pick<
  RouteWorkspaceContainerViewModelInput,
  "itinerary" | "autoFilledCount" | "intentLine" | "executionLine" | "weakestDay"
>): RouteWorkspaceOverview {
  return {
    completeness: itinerary.completion_intelligence?.trip_completeness ?? null,
    pendingTaskCount: itinerary.completion_intelligence?.action_tasks?.length ?? 0,
    autoFilledCount,
    stayAreaLabel: itinerary.stay_recommendation?.options?.[0]?.suggested_area_label ?? null,
    departureLabel:
      itinerary.departure_recommendation?.options?.[0]?.suggested_departure_label ?? null,
    realismHeadline: itinerary.planner_realism?.headline ?? null,
    realismStatus: itinerary.planner_realism?.status ?? null,
    intentLine: intentLine ?? null,
    executionLine: executionLine ?? null,
    weakestDay: weakestDay ?? null,
  };
}

export function buildRouteWorkspaceSheetCopy(
  activeSheet: RouteWorkspaceSheetKey | null,
  hasCompletionTasks = true,
  hasRouteRisk = false,
): {
  title?: string;
  description?: string;
} {
  if (activeSheet === "completion") {
    if (!hasCompletionTasks) {
      return {
        title: "路线检查",
        description: "当前没有待补齐项目；可以按需查看路线依据和已保护边界。",
      };
    }
    if (hasRouteRisk) {
      return {
        title: "补全其他信息",
        description: "这些是路线风险之外的空缺；处理它们不会替代路线风险确认。",
      };
    }
    return {
      title: "补全这条路线",
      description: "只看还缺什么、下一步怎么补，不把解释压在主路线前面。",
    };
  }

  if (activeSheet === "adjust") {
    return {
      title: "继续调整",
      description: "用一句话继续改当前计划，不需要重新填表。",
    };
  }

  if (activeSheet === "share") {
    return {
      title: "分享与导出",
      description: "把这条路线带出产品，发给朋友或留作出行参考。",
    };
  }

  if (activeSheet === "more") {
    return {
      title: "更多旅行信息",
      description: "查看系统理解、住宿离开建议和当前计划。",
    };
  }

  return {};
}

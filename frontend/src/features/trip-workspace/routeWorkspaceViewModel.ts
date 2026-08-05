import type {
  ItineraryLike,
  RouteWorkspaceOverview,
} from "@/components/trip/MobileEditRouteWorkspace";
import type { RouteWorkspaceSheetKey } from "@/components/trip/RouteWorkspaceShell";

type RouteWorkspacePlannerRealism = {
  status?: "executable" | "needs_repair" | "unstable" | string | null;
  headline?: string | null;
} | null;

export type RouteWorkspaceExecutionTrustFact = {
  key: string;
  category: "place" | "route" | "fixed_event" | "schedule" | "execution" | string;
  status: "confirmed" | "stale" | "missing" | "conflicting" | "heuristic" | "unknown" | string;
  source_kind: "provider" | "user" | "deterministic" | "heuristic" | "missing_data" | string;
  verification_status: "user_confirmed" | "provider_returned" | "unavailable" | "not_applicable" | "unknown" | string;
  freshness_status: "fresh" | "stale" | "unknown" | "not_applicable" | string;
  label: string;
  detail: string;
  count: number;
};

export type RouteWorkspaceExecutionTrust = {
  status?: "ready" | "needs_attention" | "blocked" | string | null;
  headline?: string | null;
  blocking_reasons?: string[] | null;
  warning_reasons?: string[] | null;
  facts?: RouteWorkspaceExecutionTrustFact[] | null;
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
  execution_trust?: RouteWorkspaceExecutionTrust;
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
  sheetTitle?: string;
  sheetDescription?: string;
};

export type RouteWorkspaceContainerViewModel = {
  shell: RouteWorkspaceShellViewModel;
  overview: RouteWorkspaceOverview;
  executionTrust: RouteWorkspaceExecutionTrustViewModel;
};

export type RouteWorkspaceExecutionTrustFactViewModel = {
  key: string;
  label: string;
  detail: string;
  count: number;
  stateLabel: string;
  sourceLabel: string;
  verificationLabel: string;
  freshnessLabel: string;
  tone: "stable" | "attention" | "blocked" | "neutral";
};

export type RouteWorkspaceExecutionTrustViewModel = {
  status: "ready" | "needs_attention" | "blocked";
  statusLabel: string;
  headline: string;
  blockingReasons: string[];
  warningReasons: string[];
  blockingFacts: RouteWorkspaceExecutionTrustFactViewModel[];
  warningFacts: RouteWorkspaceExecutionTrustFactViewModel[];
  contextFacts: RouteWorkspaceExecutionTrustFactViewModel[];
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
    }),
    overview: buildRouteWorkspaceOverview({
      itinerary,
      autoFilledCount,
      intentLine,
      executionLine,
      weakestDay,
    }),
    executionTrust: buildRouteWorkspaceExecutionTrustViewModel(
      itinerary.execution_trust,
      itinerary.planner_realism,
    ),
  };
}

export function buildRouteWorkspaceExecutionTrustViewModel(
  trust: RouteWorkspaceExecutionTrust | undefined | null,
  plannerRealism?: RouteWorkspacePlannerRealism,
): RouteWorkspaceExecutionTrustViewModel {
  const status = normalizeExecutionTrustStatus(trust?.status, plannerRealism?.status);
  const facts = (trust?.facts ?? []).map(buildExecutionTrustFactViewModel);
  const blockingFacts = facts.filter((fact) => fact.tone === "blocked");
  const warningFacts = facts.filter((fact) => fact.tone === "attention");
  const contextFacts = facts.filter((fact) => fact.tone === "stable" || fact.tone === "neutral");

  return {
    status,
    statusLabel:
      status === "ready" ? "执行依据可查看" : status === "blocked" ? "需要先处理" : "需要处理",
    headline:
      trust?.headline ??
      (status === "blocked"
        ? "当前路线存在执行冲突，先处理阻断项再出行。"
        : status === "needs_attention"
          ? "路线仍有需要复核的执行事实。"
          : "这版路线没有保存独立的事实新鲜度记录。"),
    blockingReasons: trust?.blocking_reasons ?? [],
    warningReasons: trust?.warning_reasons ?? [],
    blockingFacts,
    warningFacts,
    contextFacts,
  };
}

function buildExecutionTrustFactViewModel(
  fact: RouteWorkspaceExecutionTrustFact,
): RouteWorkspaceExecutionTrustFactViewModel {
  const status = fact.status;
  const state = executionFactState(status);
  const isHeuristic = status === "heuristic" || fact.source_kind === "heuristic";
  const heuristicBoundary = "系统判断不等同于用户确认事实。";
  const alreadyStatesHeuristicBoundary = /不等同于用户(?:已)?确认的?事实/.test(fact.detail);

  return {
    key: fact.key,
    label: fact.label,
    detail: isHeuristic
      ? alreadyStatesHeuristicBoundary ? fact.detail : `${fact.detail} ${heuristicBoundary}`
      : fact.detail,
    count: fact.count,
    stateLabel: state.stateLabel,
    sourceLabel: executionSourceLabel(fact.source_kind),
    verificationLabel: executionVerificationLabel(fact.verification_status),
    freshnessLabel: executionFreshnessLabel(fact.freshness_status),
    tone: state.tone,
  };
}

function normalizeExecutionTrustStatus(
  status?: string | null,
  plannerStatus?: string | null,
): RouteWorkspaceExecutionTrustViewModel["status"] {
  if (status === "blocked" || plannerStatus === "unstable") return "blocked";
  if (status === "needs_attention" || plannerStatus === "needs_repair") return "needs_attention";
  return "ready";
}

function executionFactState(status: string): Pick<RouteWorkspaceExecutionTrustFactViewModel, "stateLabel" | "tone"> {
  if (status === "conflicting") return { stateLabel: "存在冲突", tone: "blocked" };
  if (status === "missing") return { stateLabel: "信息缺失", tone: "attention" };
  if (status === "stale") return { stateLabel: "已过期", tone: "attention" };
  if (status === "heuristic") return { stateLabel: "系统判断", tone: "neutral" };
  if (status === "confirmed") return { stateLabel: "已记录", tone: "stable" };
  return { stateLabel: "未记录", tone: "neutral" };
}

function executionSourceLabel(source: string): string {
  if (source === "provider") return "来源：provider 返回";
  if (source === "user") return "来源：用户确认";
  if (source === "deterministic") return "来源：系统确定性检查";
  if (source === "heuristic") return "来源：系统建议";
  return "来源：信息未返回";
}

function executionVerificationLabel(status: string): string {
  if (status === "user_confirmed") return "确认：用户已确认";
  if (status === "provider_returned") return "确认：规划时 provider 已返回";
  if (status === "unavailable") return "确认：暂无可验证来源";
  if (status === "not_applicable") return "确认：不适用";
  return "确认：未记录";
}

function executionFreshnessLabel(status: string): string {
  if (status === "fresh") return "新鲜度：当前";
  if (status === "stale") return "新鲜度：已过期";
  if (status === "not_applicable") return "新鲜度：不适用";
  return "新鲜度：未记录";
}

export function buildRouteWorkspaceShellViewModel({
  city,
  itinerary,
  editing,
  activeSheet,
}: Pick<RouteWorkspaceContainerViewModelInput, "city" | "itinerary" | "editing" | "activeSheet">): RouteWorkspaceShellViewModel {
  const status = itinerary.planner_realism?.status;
  const sheetCopy = buildRouteWorkspaceSheetCopy(activeSheet);

  return {
    city,
    tripDays: itinerary.trip_days,
    statusLabel:
      status === "executable"
        ? "骨架可走"
        : status === "unstable"
          ? "需要重排"
          : "还有空缺",
    statusTone: status === "executable" ? "stable" : "attention",
    subtitle: editing
      ? "拖动、锁定、删除或先放进待规划，完成后这版会成为当前计划。"
      : "先顺着路线看一遍。想改顺序、删点或继续补全时，再进入编辑。",
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

export function buildRouteWorkspaceSheetCopy(activeSheet: RouteWorkspaceSheetKey | null): {
  title?: string;
  description?: string;
} {
  if (activeSheet === "completion") {
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

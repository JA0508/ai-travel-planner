"use client";

import {
  CompletionTaskCandidatePanel,
  type CompletionTaskCandidateOptionLike,
  type CompletionTaskCandidatePreviewLike,
} from "@/components/trip/CompletionTaskCandidatePanel";

export type CompletionTaskActionCardLike = {
  task_id: string;
  task_instance_key?: string | null;
  title: string;
  reason: string;
  action_prompt: string;
  priority?: "high" | "medium" | "low" | string;
};

export type CompletionTaskEditLike = {
  task_instance_key: string;
  inserted_item: { name: string };
};

type CompletionTaskActionListProps<
  TTask extends CompletionTaskActionCardLike,
  TOption extends CompletionTaskCandidateOptionLike,
> = {
  variant?: "sheet" | "rail";
  tasks: TTask[];
  expanded: boolean;
  onExpandedChange: (expanded: boolean) => void;
  getTaskInstanceKey: (task: TTask) => string;
  completionTaskEdits: CompletionTaskEditLike[];
  candidatePreviews: Record<string, CompletionTaskCandidatePreviewLike & { options: TOption[] }>;
  previewingTaskId: string | null;
  applyingTaskId: string | null;
  disabled: boolean;
  replanning: boolean;
  canPreviewTask: (task: TTask) => boolean;
  onPreviewTask: (task: TTask) => void;
  onUndoTask: (taskInstanceKey: string) => void;
  onUsePrompt: (prompt: string) => void;
  onApplyOption: (task: TTask, option: TOption) => void;
  onRejectOption: (task: TTask, option: TOption) => void;
};

export function CompletionTaskActionList<
  TTask extends CompletionTaskActionCardLike,
  TOption extends CompletionTaskCandidateOptionLike,
>({
  variant = "sheet",
  tasks,
  expanded,
  onExpandedChange,
  getTaskInstanceKey,
  completionTaskEdits,
  candidatePreviews,
  previewingTaskId,
  applyingTaskId,
  disabled,
  replanning,
  canPreviewTask,
  onPreviewTask,
  onUndoTask,
  onUsePrompt,
  onApplyOption,
  onRejectOption,
}: CompletionTaskActionListProps<TTask, TOption>) {
  if (!tasks.length) {
    return null;
  }

  const completedCount = tasks.filter((task) => {
    const taskInstanceKey = getTaskInstanceKey(task);
    return completionTaskEdits.some((edit) => edit.task_instance_key === taskInstanceKey);
  }).length;
  const pendingCount = Math.max(tasks.length - completedCount, 0);
  const rail = variant === "rail";
  const collapsedLimit = rail ? 3 : 4;
  const visibleTasks = tasks.slice(0, expanded ? undefined : collapsedLimit);

  return (
    <section
      style={{
        position: "relative",
        display: "grid",
        gap: rail ? 14 : 18,
        padding: rail ? 0 : 18,
        borderRadius: rail ? 0 : 28,
        background: rail
          ? "transparent"
          : "linear-gradient(180deg, rgba(255,253,249,0.98), rgba(247,244,238,0.94))",
        border: rail ? "none" : "1px solid var(--ec-line)",
        boxShadow: rail ? "none" : "var(--ec-shadow-1)",
      }}
    >
      {rail ? (
        <div style={{ display: "grid", gap: 10 }}>
          <div style={taskRailSummaryStyle}>
            <div style={taskRailSummaryItemStyle}>
              <strong style={taskRailSummaryValueStyle}>{pendingCount}</strong>
              <span style={taskRailSummaryLabelStyle}>优先建议</span>
            </div>
            <div style={taskRailSummaryItemStyle}>
              <strong style={taskRailSummaryValueStyle}>{completedCount}</strong>
              <span style={taskRailSummaryLabelStyle}>已补全</span>
            </div>
          </div>
        </div>
      ) : (
        <div style={{ display: "grid", gap: 8 }}>
          <p
            style={{
              margin: 0,
              color: "var(--ec-slate)",
              fontSize: 11,
              fontWeight: 900,
              letterSpacing: "0.12em",
              textTransform: "uppercase",
            }}
          >
            下一步
          </p>
          <p
            style={{
              margin: 0,
              color: "var(--ec-ink)",
              fontFamily: '"Iowan Old Style", Georgia, "Times New Roman", serif',
              fontSize: 21,
              lineHeight: 1.15,
            }}
          >
            先补最影响成行的空缺
          </p>
          <p style={{ margin: 0, color: "var(--ec-slate)", fontSize: 13, lineHeight: 1.65 }}>
            不是再生成一次长答案，而是把当前路线里最影响完成度的空缺逐项补齐。
          </p>
        </div>
      )}
      <div style={{ display: "grid", gap: rail ? 9 : 12 }}>
        {visibleTasks.map((task) => {
          const taskInstanceKey = getTaskInstanceKey(task);
          const taskEdit =
            completionTaskEdits.find((edit) => edit.task_instance_key === taskInstanceKey) ?? null;
          const taskPreview = candidatePreviews[taskInstanceKey] ?? null;
          const taskCompleted = taskEdit !== null;
          const taskScope = buildTaskScopeLabel(task);
          const taskImpact = buildTaskImpactLabel(task);
          const boundaryLabel = task.priority === "high" ? "会先检查固定边界" : "不直接改硬约束";
          return (
            <div
              key={taskInstanceKey}
              style={{
                position: "relative",
                display: "grid",
                gap: 10,
                padding: rail ? "13px 13px 13px 17px" : 16,
                borderRadius: rail ? 19 : 22,
                backgroundColor: taskCompleted
                  ? "rgba(231,236,232,0.82)"
                  : "rgba(255,253,249,0.96)",
                border: taskCompleted
                  ? "1px solid rgba(102,113,95,0.22)"
                  : "1px solid var(--ec-line-soft)",
                boxShadow: rail ? "var(--ec-shadow-1)" : "0 12px 28px rgba(21,21,21,0.04)",
              }}
            >
              {rail ? (
                <span
                  aria-hidden="true"
                  style={{
                    position: "absolute",
                    top: 0,
                    bottom: 0,
                    left: 0,
                    width: 4,
                    borderRadius: "22px 0 0 22px",
                    backgroundColor: taskCompleted
                      ? "var(--ec-moss)"
                      : task.priority === "high"
                        ? "var(--ec-ochre)"
                        : "rgba(102,113,95,0.45)",
                  }}
                />
              ) : null}
              <div style={{ display: "flex", justifyContent: "space-between", gap: 10 }}>
                <div style={{ display: "flex", gap: 9, alignItems: "start", minWidth: 0 }}>
                  {rail ? (
                    <span
                      style={taskRailDotStyle(
                        taskCompleted,
                        task.priority === "high",
                      )}
                    />
                  ) : null}
                  <p style={{ margin: 0, color: "var(--ec-ink)", fontSize: rail ? 14 : 15, fontWeight: 900, lineHeight: 1.25, textWrap: "pretty" }}>
                    {formatCompletionTaskCopy(task.title)}
                  </p>
                </div>
                <span
                  style={{
                    alignSelf: "start",
                    padding: "3px 7px",
                    borderRadius: 999,
                    backgroundColor: taskCompleted
                      ? "rgba(123, 160, 127, 0.16)"
                      : task.priority === "high"
                        ? "rgba(207, 121, 52, 0.12)"
                        : "rgba(123, 160, 127, 0.12)",
                    color: taskCompleted
                      ? "var(--ec-moss)"
                      : task.priority === "high"
                        ? "#9a5b2a"
                        : "var(--ec-moss)",
                    fontSize: 11,
                    fontWeight: 900,
                    whiteSpace: "nowrap",
                  }}
                >
                  {taskCompleted ? "已完成" : task.priority === "high" ? "优先" : "可优化"}
                </span>
              </div>
              <p style={rail ? railTaskReasonStyle : sheetTaskReasonStyle}>
                {formatCompletionTaskCopy(task.reason)}
              </p>
              {rail ? (
                <div style={taskRailMetaGridStyle}>
                  <span>{taskImpact}</span>
                  <span>{taskScope}</span>
                  <span>{boundaryLabel}</span>
                </div>
              ) : null}
              {taskEdit ? (
                <p style={{ margin: 0, color: "var(--ec-moss)", fontSize: 13, fontWeight: 800 }}>
                  已补入：{taskEdit.inserted_item.name}
                </p>
              ) : null}
              <div style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
                {taskEdit ? (
                  <button
                    type="button"
                    disabled={disabled}
                    onClick={() => onUndoTask(taskInstanceKey)}
                    className="ec-interactive-pill"
                    style={{
                      border: "1px solid rgba(123, 160, 127, 0.22)",
                      borderRadius: 999,
                      padding: "8px 12px",
                      backgroundColor: "rgba(255,255,255,0.76)",
                      color: "var(--ec-moss)",
                      cursor: disabled ? "not-allowed" : "pointer",
                      fontSize: 12,
                      fontWeight: 900,
                    }}
                  >
                    撤销本次补全
                  </button>
                ) : (
                  <>
                    <button
                      type="button"
                      disabled={disabled}
                      onClick={() => onPreviewTask(task)}
                      className="ec-interactive-pill"
                      style={{
                        border: "1px solid rgba(154, 106, 47, 0.18)",
                        borderRadius: 999,
                        padding: "8px 12px",
                        backgroundColor: "rgba(154, 106, 47, 0.12)",
                        color: "var(--ec-clay)",
                        cursor: disabled ? "not-allowed" : "pointer",
                        fontSize: 12,
                        fontWeight: 900,
                      }}
                    >
                      {previewingTaskId === taskInstanceKey
                        ? "找候选中..."
                        : applyingTaskId === taskInstanceKey
                          ? "补齐中..."
                          : replanning
                            ? "优化中..."
                            : canPreviewTask(task)
                              ? "查看建议"
                              : "按这句优化"}
                    </button>
                    <button
                      type="button"
                      disabled={disabled}
                      onClick={() => onUsePrompt(task.action_prompt)}
                      className="ec-interactive-pill"
                      style={{
                        border: "1px solid rgba(154, 106, 47, 0.14)",
                        borderRadius: 999,
                        padding: "8px 12px",
                        backgroundColor: "rgba(255,255,255,0.72)",
                        color: "var(--ec-slate)",
                        cursor: disabled ? "not-allowed" : "pointer",
                        fontSize: 12,
                        fontWeight: 800,
                      }}
                    >
                      调整条件
                    </button>
                  </>
                )}
              </div>
              {!taskCompleted && taskPreview ? (
                <CompletionTaskCandidatePanel
                  preview={taskPreview}
                  disabled={disabled}
                  applying={applyingTaskId === taskInstanceKey}
                  onApplyOption={(option) => onApplyOption(task, option)}
                  onRefreshOptions={() => onPreviewTask(task)}
                  onRejectOption={(option) => onRejectOption(task, option)}
                />
              ) : null}
            </div>
          );
        })}
      </div>
      {tasks.length > collapsedLimit ? (
        <button
          type="button"
          onClick={() => onExpandedChange(!expanded)}
          className="ec-interactive-pill"
          style={{
            border: "1px solid rgba(154, 106, 47, 0.14)",
            borderRadius: 999,
            padding: "8px 11px",
            backgroundColor: "rgba(255,255,255,0.72)",
            color: "var(--ec-slate)",
            cursor: "pointer",
            fontSize: 12,
            fontWeight: 900,
            justifySelf: "start",
          }}
        >
          {expanded ? "收起部分建议" : `查看其余 ${tasks.length - collapsedLimit} 个建议`}
        </button>
      ) : null}
    </section>
  );
}

const taskRailSummaryStyle = {
  display: "grid",
  gridTemplateColumns: "repeat(2, minmax(0, 1fr))",
  gap: 8,
} as const;

const taskRailSummaryItemStyle = {
  display: "grid",
  gap: 2,
  padding: "10px 12px",
  borderRadius: 16,
  backgroundColor: "rgba(255,253,249,0.92)",
  color: "var(--ec-ink)",
  border: "1px solid var(--ec-line)",
} as const;

const taskRailSummaryValueStyle = {
  color: "var(--ec-ink)",
  fontSize: 22,
  lineHeight: 1,
} as const;

const taskRailSummaryLabelStyle = {
  color: "var(--ec-slate)",
  fontSize: 12,
} as const;

const railTaskReasonStyle = {
  margin: 0,
  color: "var(--ec-slate)",
  fontSize: 12,
  lineHeight: 1.5,
  display: "-webkit-box",
  overflow: "hidden",
  WebkitBoxOrient: "vertical",
  WebkitLineClamp: 3,
} as const;

const sheetTaskReasonStyle = {
  margin: 0,
  color: "var(--ec-slate)",
  fontSize: 13,
  lineHeight: 1.6,
} as const;

const taskRailMetaGridStyle = {
  display: "grid",
  gap: 6,
  padding: 9,
  borderRadius: 14,
  backgroundColor: "rgba(247,244,238,0.72)",
  border: "1px solid var(--ec-line-soft)",
  color: "var(--ec-slate)",
  fontSize: 11,
  fontWeight: 800,
  lineHeight: 1.35,
} as const;

function taskRailDotStyle(completed: boolean, highPriority: boolean) {
  return {
    width: 10,
    height: 10,
    marginTop: 4,
    borderRadius: 999,
    backgroundColor: completed
      ? "#7ba07f"
      : highPriority
        ? "#cf7934"
        : "#9aa9a0",
    boxShadow: completed
      ? "0 0 0 5px rgba(123,160,127,0.12)"
      : highPriority
        ? "0 0 0 5px rgba(207,121,52,0.12)"
        : "0 0 0 5px rgba(154,169,160,0.12)",
    flex: "0 0 auto",
  };
}

function formatCompletionTaskCopy(value: string) {
  const normalized = value.toLocaleLowerCase();
  if (normalized.includes("auto-seeded from sparse city input")) {
    return normalized.includes("meal")
      ? "系统发现这一天缺少真实用餐停顿，建议先补一个顺路餐食点。"
      : "系统发现这一天缺少可执行停留点，建议先补一个能串起路线的地点。";
  }
  if (normalized.includes("system added this meal anchor")) {
    return "系统建议补一个餐食锚点，避免这一天只剩景点堆叠。";
  }
  if (normalized.includes("amap identifies this as")) {
    return "已用高德地点信息校验类型与位置，候选可继续查看后再补入。";
  }
  const translated = value
    .replace(/\bDay\s*(\d+)\b/gi, "第 $1 天")
    .replace(/\bmorning\b/gi, "上午")
    .replace(/\bafternoon\b/gi, "下午")
    .replace(/\bevening\b/gi, "晚上")
    .replace(/\blunch anchor\b/gi, "午餐锚点")
    .replace(/\bdinner anchor\b/gi, "晚餐锚点")
    .replace(/\bmeal anchor\b/gi, "餐食锚点")
    .replace(/\blunch\b/gi, "午餐")
    .replace(/\bdinner\b/gi, "晚餐")
    .replace(/\bsparse\b/gi, "偏空")
    .replace(/\bblock\b/gi, "时段")
    .replace(/\bstop\b/gi, "地点")
    .replace(/\broute\b/gi, "路线")
    .replace(/补齐\s+第/g, "补齐第")
    .replace(/第\s+(\d+)\s+天/g, "第 $1 天")
    .replace(/第\s+(\d+)\s+天\s+(上午|下午|晚上)/g, "第 $1 天$2")
    .replace(/\s+的/g, "的");
  if (!/[\u3400-\u9fff]/.test(translated) && /[a-z]{4,}/i.test(translated)) {
    if (normalized.includes("meal") || normalized.includes("food") || normalized.includes("restaurant")) {
      return "补一个餐食/休息点，让这一天的路线更像真实出行。";
    }
    if (normalized.includes("evening") || normalized.includes("night")) {
      return "补一个晚间活动，让当天不要太早结束。";
    }
    return "补一个更顺路的地点，让当前路线先稳定下来。";
  }
  return translated;
}

function buildTaskImpactLabel(task: CompletionTaskActionCardLike): string {
  const text = `${task.title} ${task.reason}`;
  if (task.priority === "high") {
    return "收益：优先提升可执行性";
  }
  if (/meal|food|restaurant|餐|午|晚/.test(text)) {
    return "收益：稳住餐食节奏";
  }
  if (/evening|night|夜|晚上/.test(text)) {
    return "收益：补强夜间收口";
  }
  return "收益：减少临场决策";
}

function buildTaskScopeLabel(task: CompletionTaskActionCardLike): string {
  const text = `${task.title} ${task.reason} ${task.action_prompt}`;
  const dayMatch = text.match(/(?:第\s*)?(\d+)\s*(?:天|day)/i);
  if (dayMatch) {
    return `影响：Day ${dayMatch[1]}`;
  }
  if (/route|路线|跨区|移动/.test(text)) {
    return "影响：路线连接";
  }
  if (/hotel|住宿|离开|出发/.test(text)) {
    return "影响：住宿/离开边界";
  }
  return "影响：当前时间线";
}

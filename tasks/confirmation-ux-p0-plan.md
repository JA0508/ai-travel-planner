# Confirmation UX P0 — 可信确认工作台实施计划

## 目标

把 Draft Intent 的确认页从重复的“阻塞表单堆叠”改成一个连续、可理解、可恢复的确认工作台。

用户应先看见系统已理解的旅行边界，再只处理真正阻塞生成路线的项目；每确认一项，界面立即收敛。这个阶段不改变规划器、地点核验规则、Draft Intent revision 或 handoff 的权威边界。

## 为什么现在优先

当前确认页是从用户输入进入第一版路线的唯一入口。把未知地点、缺失固定安排地点、解析问题都渲染成同样的大面积警示表单，会让用户误以为系统失败，且无法理解哪些信息来自自己、哪些需要操作。

Round 29 收口后，本 P0 置于 Opening-Hours Temporal Feasibility 之前；它让既有规划能力可被自然使用，而非新增一套聊天或地图产品。

## 产品与架构边界

保留：

- `TripIntentEnvelope`、`PlaceIdentity`、`FixedEventIntent`、Draft revision 与 idempotency。
- 未核验地点不能进入 planner handoff。
- 真实固定安排的时间边界不因 UI 重构而变化。
- 现有 `confirm_place_identity`、`update_fixed_event`、clarification、preview/apply API。

不做：

- 不自动确认地点；候选永远只是建议，必须由用户明确采用。
- 不在确认页伪造地图、照片、评分、路线时间或地点候选。
- 不在本 P0 实现 Chat × Live Map；该能力在确认链路稳定后作为 Compose Workspace 独立计划。
- 不把普通输出要求或泛化“活动”重新解释为固定安排。

## 目标体验

```text
你的重庆旅行，已经整理好了
重庆 · 3 天 · 轻松 · 与朋友同行

已理解
  抵达 / 离开边界、住宿区域、旅行节奏、必去地点

还差 2 项即可生成路线
  1. 确认「洪崖洞」是哪一处            [选择地点]
  2. 补充 9 月 12 日 19:00 预约的地点   [搜索地点]

已确认
  ✓ 解放碑 · 重庆市渝中区

[修改原始需求]                 [生成路线预览]
```

### 确认队列规则

1. 每个真实阻塞项只出现一次，按影响程度排序。
2. `must` 地点、固定安排地点和基础信息澄清使用同一条确认队列，但保留各自的业务语义。
3. 未展开项仅显示标题、原因和一个可操作动作；不默认展示大表单。
4. 选择 provider 候选后，项目折叠为“已确认”行，并更新剩余数量与底部 CTA。
5. 真实时间冲突才使用警示色；缺少地点是待办，不是错误。
6. “修改原始需求”必须打开已有的编辑路径或回到输入页，不能是无行为按钮。

## 设计系统（v0）

- **叙事角色**：从自然语言到可执行路线之间的“编辑台”，不是错误诊断页。
- **观看距离**：桌面优先，760px 以下单列；移动端所有触控目标不少于 44px。
- **视觉温度**：安静、可信、带旅行编辑感。延续项目的 warm white、深墨、苔绿和赭石；红色只表示真正的冲突。
- **版式**：单一 920–1120px 内容列。顶部为旅程摘要，中段为一个主确认队列，底部为固定动作区；依据和导入资料保持渐进披露。
- **组件语言**：细边界、短圆角、无渐变、无徽章墙。确认项使用紧凑的路线清单，而非重复的大卡片。
- **动效**：确认成功后项目缩为已确认行；遵守 `prefers-reduced-motion`，不以动效表达关键状态。

## 批次与验收

### P0.0 — 体验模型与回归契约

**范围**：将现有 `view.blockers`、未核验 `PlaceIdentity` 和 fixed event 收敛为前端专用、可排序的确认队列 view model；不更改 API。

**完成标准**：

- 队列区分 `must_place`、`fixed_place`、`clarification`、`conflict` 与已确认项目。
- 同一业务问题不会同时出现在泛化 blocker 与专用地点区。
- 固定安排仅在存在真实 `fixed_events` 时出现。
- 对应 model tests 覆盖空态、多个地点、固定安排、冲突与已确认收敛。

**主要文件**：

- `frontend/src/features/preplan-intent/prePlanConfirmationModel.ts`
- `frontend/src/features/preplan-intent/prePlanConfirmationModel.test.ts`

### P0.1 — 可看的确认工作台、地点推荐与快捷编辑

**范围**：拆出展示型 Confirm Queue / Confirmed Items / Trip Summary 组件，接回现有 edit、identity confirmation 和 preview 操作；为未核验地点补充只读 provider 候选建议与就地搜索。

**地点建议边界**：

- 初始 provider 候选按原始地点名称和目的地确定性排序，第一项仅标记为“系统推荐”。
- 用户点击“采用这个地点”才提交 `confirm_place_identity`；服务端依据记录的查询词重新读取 provider，绝不信任浏览器提交的坐标或地点详情。
- “换一个 / 搜索地点”只是只读检索；它不创建 Draft revision，也不改变原始地点语义。
- 不渲染照片、评分、路线时间、距离或置信度，除非另有真实、已验证的 provider 事实契约。

**完成标准**：

- 页面默认显示“已理解”“还需确认”“已确认”三个明确区域。
- 缺少地点不使用红色错误容器；时间冲突仍是警示。
- 确认候选后仅该项目更新，不丢失其他 Draft 状态。
- 首个 provider 候选以“系统推荐”呈现，并有清楚、不可伪装成事实的推荐依据。
- 无初始候选时可直接搜索更具体的地点；搜索本身没有写入副作用。
- 从搜索结果采用地点时，确认 mutation 带上查询词，由服务端重新核验 provider ID 后再追加 revision。
- 生成按钮显示明确剩余项与不可用原因；`onCancel` 有可读的“修改原始需求”文案。
- 不出现假的地图、评分、图片或无行为按钮。

**主要文件**：

- `frontend/src/features/preplan-intent/PrePlanIntentWorkspace.tsx`
- `frontend/src/features/preplan-intent/PrePlanConfirmationQueue.tsx`
- `frontend/src/features/preplan-intent/draftIntentEditApi.ts`
- `backend/app/services/place_identity_resolution.py`
- `backend/app/trips/service.py`
- `backend/app/api/routes/trips.py`
- `frontend/src/app/globals.css`
- `frontend/src/features/preplan-intent/prePlanIntentWorkspace.smoke.test.tsx`

### P0.2 — 状态、可访问性与响应式收口

**范围**：补齐加载、无候选、网络失败、stale revision、键盘焦点和移动端状态。

**完成标准**：

- 队列有语义标题、状态通知和可见 focus ring。
- 候选操作、编辑和失败重试不会丢失输入。
- 760px 以下单列显示，CTA 不遮挡内容。
- 使用 `prefers-reduced-motion` 降低确认收敛动画。

### P0.3 — 真实流程验证与设计复盘

**范围**：以 fixture 和本地真实 provider 配置分别验证“全部已确认”和“仍有一个待确认”两条路径；做一次五维 UI critique。

**完成标准**：

- 浏览器测试覆盖创建 Draft → 确认地点 → 预览路线的关键路径。
- 不将 provider 不可用显示为已确认或安全。
- `npm run typecheck`、`npm run test:workspace`、相关浏览器测试与 `git diff --check` 通过。
- 与用户共同查看 v0 后，再决定是否进入 Compose Workspace。

## 顺序与检查点

```text
Round 29 release gate / review
  → P0.0 体验模型
  → P0.1 可看的 v0  ── 用户视觉检查点
  → P0.2 状态与响应式
  → P0.3 浏览器验证与复盘
  → Opening-Hours Temporal Feasibility
  → Compose Workspace（单独立项）
```

## 风险与防护

| 风险 | 防护 |
| --- | --- |
| 为了简洁而绕过地点核验 | UI 只调用现有确认 mutation；未核验项继续阻止 handoff。 |
| 旧 Draft 同时出现历史 blocker 与新队列项 | 由 P0.0 统一去重，先加 characterization tests。 |
| 重构破坏 stale/idempotency 行为 | 复用现有 request owner，保留 focused contract tests。 |
| Mindtrip 式地图变成伪精度 | 地图与详情卡只在 verified place / provider data 已存在时另行实现。 |

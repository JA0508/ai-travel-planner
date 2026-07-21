# AI 旅行规划产品深度研究与 Codex 实施规格

> 研究对象：`JA0508/ai-travel-planner` 及主流旅行规划、行程组织、地图策展、旅中执行与旅行复盘产品。
>
> 版本日期：2026-07-12。本文件为产品研究与工程规格，不直接修改项目代码。

## 文档使用方式

- **产品决策者**：优先阅读“执行摘要、当前仓库判断、产品定位、路线图”。
- **UI/UX 设计**：阅读“竞品拆解、主流 UI 模式、信息架构”。
- **Codex/工程执行**：从“Codex 实施总则”和 F-001～F-020 开始；每个功能都包含边界、数据、API、异常和验收。
- **研究可信度**：产品能力优先采用官网；二级来源只用于补充无法从官网读取的圆周旅迹细节，并已标注。论文和 GitHub 用于技术边界与评估，不把 demo README 当生产能力证明。

## 权威与时效

本文件包含 2026-07-12 的产品研究、路线规划和当时仓库观察。实施时的权威顺序为：

```text
code / schemas / tests
→ ADRs
→ CURRENT_PHASE
→ PRODUCT_DIRECTION
→ CODEX product specification
→ research snapshots
```

其中的历史 LOC、历史缺口、旧阶段判断和竞品研究不得直接当作当前代码事实。Codex 开始任何 F-xxx 实施前，必须重新审计当前 `main` 的真实代码、schema、API、状态 owner、tests、ADR 和 `docs/product/CURRENT_PHASE.md`。

---

## 1. 执行摘要

### 1.1 最重要的判断

你的项目不应该继续被定义为“AI 帮我生成三天旅游路线”。这类能力已经高度同质化，任何大模型加地图 API 都能做出表面可用的 demo。真正有辨识度的定位应当是：

> **Source-to-Executable Trip Workspace：把散乱攻略、个人偏好、时间边界、固定安排和真实预订，编译成可解释、可验证、可协作、可动态修复的旅行执行方案。**

更适合项目内部使用的中文产品概念是：**“AI 行程编译器 / 可执行旅行工作台”**。

### 1.2 为什么这个方向更有含金量

- 圆周旅迹、Mindtrip、Placify 证明：用户常常已经拥有攻略、截图、链接和收藏，真正的痛点是把碎片转成结构化行程，而不是从空白聊天。 [S02][S10][S12]
- Wanderlog、Tripsy、TripIt 证明：成熟旅行产品最终都要容纳预订、协作、费用、文档、清单、日历和旅中状态，而不只是景点列表。 [S04][S05][S08]
- TravelPlanner、TripTailor、Flex-TravelPlanner 和 GroupTravelBench 说明：多约束、动态变化和多人偏好仍是 LLM 的弱项；仅靠语言模型很难稳定保证可行性、公平性和约束优先级。 [S16][S17][S18][S19]
- 你的仓库已经有 Intent、确定性 Scheduler、Completion Intelligence、Planner Realism、Trip Readiness、Route Workspace 和 Place Intelligence，这恰好是大多数竞品“视觉有、执行证据弱”的反面优势。 [S01]

### 1.3 推荐的产品护城河

1. **来源可追溯**：每个地点、约束和事实知道从哪篇攻略、哪张截图、哪个用户或哪个 provider 来。
2. **约束可编译**：自然语言最终落成 hard/soft/assumption 三类结构，不让 LLM 随意调度。
3. **执行可验证**：路线时间、开放状态、固定事件、到离边界、餐食节奏和多人限制有明确检查。
4. **修复是 patch，不是重写**：任何 AI 调整先展示改动、影响和受保护边界，支持部分接受与撤销。
5. **协作是决策系统，不只是共享链接**：点赞、反对、评论、个人限制、冲突和折中方案进入结构化数据。
6. **研究可复现**：同一 Intent、provider snapshot 和 planner version 可以重放；CI 有固定基准。

### 1.4 不建议优先做的事情

- 不优先做完整酒店/机票搜索和支付；这会把项目拖向 OTA，数据和商业接入成本远高于作品集价值。
- 不优先做公开旅行社区、达人内容流和复杂推荐 feed。
- 不用一个更大的聊天框替换当前结构化工作区。
- 不追求一次性全局最优路线算法；先保证边界、证据、局部修复和可观察。
- 不把现有 8,984 行 `page.tsx` 继续作为所有新功能的容器。

---

## 2. 当前仓库真实能力与缺口

### 2.1 已经具备的高价值能力

- **自然语言与结构化输入并存**：存在 `planFromText`、`parseTripIntent`、`parsePlanningState`、availability preview 等端点和表单同步逻辑。
- **确定性排程**：按 morning/afternoon/evening 时间块、固定日/固定时间、可用窗口、空间/交通启发式进行编排。
- **酒店可选、兴趣优先**：用户不需要先选酒店；路线骨架可以先生成，再建议住宿区域。
- **Completion Intelligence**：完整度、密度、餐食、夜间、交通边界、自动补入和行动任务。
- **Planner Realism 与 Trip Readiness**：明确 executable/needs_repair/unstable，前端再映射为 ready/minor-gaps/needs-attention/not-ready；展示首要问题、影响、受保护边界和下一步动作。
- **Route Workspace**：桌面左侧准备/行动、中央地图、右侧时间线/地点详情；移动端路线编辑、Day 切换、未排程池、撤销/重做和路线预览。
- **Place Intelligence**：Trust、Route Fit、Visit Context、Caveats、Evidence 和 Actions 已被拆成独立卡片，方向非常正确。
- **工程防护**：readiness 端点、request id、process time、idempotency key、provider fallback、frontend typecheck/build 和 backend tests。

### 2.2 当前架构中最需要优先处理的问题

1. **单页过重**：`frontend/src/app/page.tsx` 约 8,984 行，混合类型、输入流程、生成、编辑、补全、分享和大量状态；它会放大 change impact。
2. **缺少长期 Trip 主体**：README 明确没有认证；当前更像单次会话，无法自然承载协作、预订、费用和旅行后数据。
3. **缺少统一来源模型**：已有 POI research，但尚未形成“原始内容 → mention → canonical place → fact/evidence → itinerary item”的完整 provenance graph。
4. **旅行生命周期不完整**：强在“规划结果”，弱在导入、多人决策、预订整理、旅中执行、异常修复和旅行复盘。
5. **前端依赖极简**：Next/React 外无专门地图、状态、拖拽、表单或数据请求库。优点是可控，缺点是复杂交互容易重复造轮子；是否引入依赖必须由具体问题驱动。

### 2.3 推荐保留不动的架构原则

- LLM：理解、分类、建议、解释、生成候选。
- Deterministic layer：身份解析、坐标/路线、日期时间、硬约束、权限、版本、patch 应用、验证、事实时效。
- 任何 LLM 输出进入执行层前必须变成 schema-valid 的结构化输入。
- 所有“实时、营业、距离、票价、已预订”事实必须有来源，不由 LLM 常识补齐。
- 功能增长不能破坏现有 scheduler contract；优先通过 adapter 和新 domain 扩展。

---

## 3. 竞品版图：不是一类 App，而是六种产品

| 类型 | 代表产品 | 核心价值 | 对本项目最值得借鉴 |
|---|---|---|---|
| 攻略转行程 | 圆周旅迹、Mindtrip | 把内容碎片变成地点和路线 | Universal Import + Review Inbox |
| 行程协作工作台 | Wanderlog、Tripomatic | 地图、时间线、路线、协作、预算 | Trip 数据模型、未排程池、按天拖拽 |
| 预订运营助手 | TripIt、Tripsy | 自动整理预订、旅中提醒、文档 | Booking Inbox、实时状态、权限 |
| 自驾专用 | Roadtrippers | 沿路线发现、车辆约束、油费、RV | detour cost、vehicle profile、route corridor |
| 地点知识库 | Placify | 长期收藏、集合、个人地图 | Place Library、Collections、复用 |
| 旅行记录/复盘 | Polarsteps、圆周旅迹足迹 | 自动轨迹、故事、统计、分享 | Planned vs Actual、Recap、Footprints |

---

## 4. 逐个产品功能与 UI 深度拆解

### 4.1 圆周旅迹

**产品类型**：中国移动端“内容导入 → 行程生成 → 地图执行 → 足迹沉淀”

**核心闭环**：把小红书、微信、攻略文字、图片等碎片内容交给系统，抽取地点和时间，生成按天路线；用户再拖动、补充、共享，旅行中查看地图和天气，旅行后沉淀足迹。

**主流功能**

- 链接、长文本、图片/截图的统一导入入口；核心价值不是“问 AI”，而是把已有攻略转成结构化地点。
- 自动识别城市、日期、景点、餐厅、路线和时间片，并把候选地点映射到真实 POI。
- 按天展示地点序列，地图同步绘制路线；支持长按排序、增删地点和交通方式切换。
- 多人通过社交链路进入同一行程协作，适合旅行群快速共建。
- 地点详情融合地址、图文笔记、评价、备注和“为什么加入此行程”。
- 行程概览整合天气、日程、路线和城市切换；旅行中更像执行工具而非内容社区。
- 足迹地图、城市点亮、相册导入和旅行记录形成复访与长期留存。

**UI 与交互结构**

- 首页首要 CTA 是“创建/导入行程”，而不是长篇聊天窗口；入口承担识别链接、文字、图片的统一任务。
- 核心工作区是移动端地图与底部行程卡片的联动：地图负责空间关系，列表负责顺序、时间与编辑。
- 日切换使用横向 Day 标签；地点卡片使用序号、图标、时间、路程信息和拖拽把手，认知成本低。
- 地点详情通常以全屏页或底部抽屉出现，返回后保持原 Day 和地图视口。
- 足迹页面强调视觉情绪和成就感，颜色更活跃，和“规划工作台”的理性界面形成分区。

**优势**：最强启发是“把用户已有内容转成路线”，降低空白输入成本；同时用足迹完成旅行生命周期闭环。

**风险/局限**：若抽取后的 POI 匹配、开放时间和交通现实性缺少证据层，路线可能好看但不够可信。

**对本项目的直接启发**：你的项目应吸收“统一导入”和“足迹留存”，但保持现有的可解释约束、真实性检查和修复机制，做出更专业的可执行版本。

来源：[S02][S03]

### 4.2 Wanderlog

**产品类型**：全能型旅行协作与组织工作台

**核心闭环**：创建旅行 → 收集地点/攻略 → 按天排程 → 地图看距离 → 导入预订 → 协作、预算、清单 → 离线执行。

**主流功能**

- 行程时间线和地图同屏；地点间距离、预计交通时间和访问时段直接显示。
- 路线优化、道路旅行站点搜索、指南一键加入、地点评分与营业信息。
- 转发预订邮件或扫描 Gmail，自动归档航班、酒店、租车和活动。
- 多人实时协作、任务清单、打包清单、预算与费用分摊。
- 附件、离线访问、航班更新、导出到地图工具。

**UI 与交互结构**

- 桌面端使用左侧行程/收藏、中央地图或地图并列、右侧细节的密集工作区，信息密度高。
- 地点卡片可直接拖入 Day；“未排程地点”作为独立池，避免用户收藏后立刻被强制排期。
- 协作、预算、清单和预订不是散落菜单，而是同一 Trip 下的多个标签页。
- 高级能力通过上下文按钮暴露，例如选中 Day 后显示优化路线、添加地点、添加备注。

**优势**：覆盖旅行前组织和多人协作最完整，是“Trip OS”型参考。

**风险/局限**：功能面过宽、界面较重；如果全盘复制，个人项目很容易成为普通 CRUD 集合。

**对本项目的直接启发**：只借鉴统一 Trip 数据模型、未排程池、协作/预订/预算模块化，不应直接复制所有功能。

来源：[S04]

### 4.3 TripIt / TripIt Pro

**产品类型**：预订信息聚合与旅中运营助手

**核心闭环**：用户完成预订 → 转发确认邮件 → 系统自动构建主行程 → 航班/机场/风险实时更新。

**主流功能**

- 解析确认邮件，自动合并航班、酒店、租车、活动，解决“信息散落在邮箱”的问题。
- 航班状态、值机提醒、票价下降、座位变化、替代航班和风险通知。
- Go Now 出发提醒、机场可搜索地图、登机口连接路线、行李转盘信息。
- 护照续期、国家旅行信息、文档/二维码/PDF 附件和指定联系人自动共享。

**UI 与交互结构**

- 主界面以时间顺序的“Master Itinerary”呈现，预订卡片比景点内容更重要。
- 旅中状态使用高优先级通知与颜色状态，而不是让用户主动刷新。
- 机场与航班详情采用任务导向：下一步是什么、何时离开、去哪个航站楼。

**优势**：把旅行中最容易出错的实时信息转成明确行动，是旅中模式的最佳参考。

**风险/局限**：依赖高质量邮件解析、航班数据和推送基础设施，成本与合规要求较高。

**对本项目的直接启发**：先做“预订收件箱 + 结构化卡片 + 手动确认”，再逐步接实时数据，不要一开始承诺全自动。

来源：[S05]

### 4.4 Tripsy

**产品类型**：Apple 生态下的高质感旅行资料管理器

**核心闭环**：导入预订 → 统一时间线 → 同步日历 → 分享给同行人 → 管理费用和文档 → 生成旅行统计。

**主流功能**

- 预订邮件导入，航班、住宿、活动和路线统一整理。
- 实时航班延误、登机口、行李信息和日历同步。
- 协作者与只读访客；文档、费用可以单独控制可见性。
- 多币种费用、备注、照片、链接、文档和旅行统计。

**UI 与交互结构**

- 视觉克制、留白充足、卡片层级清晰；强调系统字体、原生动效和日历式时间线。
- 权限不是单一“分享链接”，而是邀请流程中的显式选择。
- 关键旅行文档用统一附件卡展示，二维码和票据在旅中可快速打开。

**优势**：演示了“高级感”不依赖炫技，而依赖信息层级、权限细节和原生交互完整性。

**风险/局限**：Apple-first 体验难以直接移植到跨端 Web；功能偏组织而非智能规划。

**对本项目的直接启发**：你的 UI 应学习其克制和任务清晰度，并把现有可解释智能作为差异化。

来源：[S08]

### 4.5 Tripomatic

**产品类型**：地图驱动的按天行程编辑器

**核心闭环**：探索目的地 → 添加地点 → 按天拖拽 → 选择交通方式 → 智能路线 → 离线导航与导出。

**主流功能**

- 按兴趣、节奏和旅行风格生成初稿。
- 数百万 POI、营业时间、当地提示和隐藏地点。
- 按天拖拽、时间估算、步行/公交/驾车/骑行/徒步路线。
- 离线地图、PDF/GPX/KML 导出、费用、协作、复制行程和备注。

**UI 与交互结构**

- 地图是主画布，列表是地图的结构化控制器；用户从地图探索，也能从时间线理解一天。
- 交通方式属于 Day 或路线段的设置，不隐藏在全局偏好中。
- 导出与离线是成熟产品的显式能力，便于用户脱离平台继续使用。

**优势**：路线编辑模型成熟，特别适合借鉴多模式和离线输出。

**风险/局限**：POI 内容量与全球数据覆盖是重资产，个人项目不应直接竞争。

**对本项目的直接启发**：聚焦“用户已选 POI 的编排和验证”，用外部数据做证据，不做全球目的地百科。

来源：[S07]

### 4.6 Roadtrippers

**产品类型**：自驾/房车场景的路线走廊发现与执行

**核心闭环**：起点终点/车辆 → 自动或手动规划 → 沿途搜索 → 加入停靠点 → 估算油费 → 导航/离线执行。

**主流功能**

- Autopilot 基于大量真实路线生成自驾方案；也支持完全手动。
- 沿路线走廊搜索景点、餐饮、营地和“值得绕路”的地点。
- 车辆档案、燃油类型、油耗、油费估算；RV 尺寸约束和专用导航。
- 多人协作、实时交通、离线地图、行程导出和大量停靠点。

**UI 与交互结构**

- 创建流程首先问起终点、车辆和规划方式，先锁定硬边界再推荐内容。
- 地图上的搜索不是“附近”，而是“沿路线增加多少绕行”的走廊式发现。
- 地点卡强调 detour cost、类别和路线影响，而不只是评分。

**优势**：把交通工具特征纳入约束，是“现实性”设计的典型。

**风险/局限**：自驾专用数据和导航责任较重。

**对本项目的直接启发**：把“路线影响/绕行成本”加入你的 Place Detail 和替换建议，会比普通推荐更有含金量。

来源：[S06]

### 4.7 Mindtrip

**产品类型**：多模态内容到行程的 AI 原生旅行工作台

**核心闭环**：从对话、网页、图片、截图、PDF 或保存地点开始 → 自动建集合/行程 → 地图与评价佐证 → 群组协作和继续对话调整。

**主流功能**

- Start Anywhere：旅行文章、图片、截图、PDF 等都能成为行程或地点清单。
- 对话式请求、个性化、地图、照片、评价和活动信息。
- 导入 Google Maps 保存点，按目的地/主题/氛围组织 Collections。
- 群组聊天、点赞、评论、@AI，以及预订凭证/收据上传。

**UI 与交互结构**

- AI 对话是入口和持续编辑器，但生成后会落到结构化 Trip/Collection，而不是停留在聊天文本。
- 内容卡与地图并列，用户能看到“建议来自哪里”，并一键加入计划。
- 群组决策通过点赞、评论和引用地点完成，降低多人聊天中信息丢失。

**优势**：最接近“AI 原生但仍结构化”的产品范式。

**风险/局限**：推荐质量和自动更新若不稳定，会造成“漂亮但不可控”的体验。

**对本项目的直接启发**：你的项目应把对话作为结构化 patch 的入口；每次调整都显示影响范围、受保护边界和可撤销变更。

来源：[S10]

### 4.8 Layla

**产品类型**：AI 灵感与预订转化型旅行助手

**核心闭环**：对话输入目的地/预算/风格 → 生成多城市行程 → 比较航班酒店活动 → 跳转或完成预订。

**主流功能**

- 日期、目的地、预算、节奏和旅行风格个性化。
- 航班、酒店、活动、餐饮聚合与价格/可用性展示。
- 多城市、道路旅行和跨交通方式路线。
- 隐藏地点和创作者视频作为灵感入口。

**UI 与交互结构**

- 首页以对话框和大幅目的地视觉吸引用户，适合“还不知道去哪”的早期阶段。
- 生成结果与可预订商品连接紧密，卡片强调价格和 CTA。
- 路线编辑深度通常让位于快速转化，和你的产品定位不同。

**优势**：灵感到方案的速度快，商业闭环明确。

**风险/局限**：容易退化成 OTA 上层聊天壳；价格和库存接入带来高成本。

**对本项目的直接启发**：你的项目可保留“决策前灵感”，但应避免把主要价值转向预订分销。

来源：[S11]

### 4.9 Polarsteps

**产品类型**：自动旅行轨迹与回忆产品

**核心闭环**：计划路线 → 后台自动记录 → 添加照片/视频/故事 → 亲友关注 → 旅行后生成统计、Reel 和旅行书。

**主流功能**

- 行程概览和个性化提示。
- 低耗电、离线可用的自动轨迹记录。
- 照片、视频、文字故事与路线绑定；亲友可跟随。
- 国家/里程等统计、Reel、纸质 Travel Book、隐私控制。

**UI 与交互结构**

- 地图路线与故事时间线是核心，不强调复杂编辑器。
- 旅行后用大图、轨迹动画、统计数字制造情感回报。
- 公开、好友和私密边界清楚，适合真实位置数据。

**优势**：解决“旅行结束后为什么还回来”的留存问题。

**风险/局限**：持续定位涉及隐私、耗电与平台权限，Web MVP 不宜立即实现。

**对本项目的直接启发**：先做轻量“完成地点 + 照片 + 旅行总结”，后续再考虑自动轨迹。

来源：[S09]

### 4.10 Placify（原 exping）

**产品类型**：个人地点知识库与地图策展工具

**核心闭环**：从任意 App 保存地点 → 建集合/主题地图 → 自定义路线与智能排序 → 分享地图 → 回顾照片和记忆。

**主流功能**

- 从 Google Maps、Instagram、Tripadvisor、TikTok、小红书、搜索和照片等来源保存地点。
- 自定义集合、筛选、分组、路线、智能排序和 Flyover 浏览。
- 地图分享、回忆、智能分类、隐私优先、本地存储和 iCloud 同步。
- 产品路线中包含协作、附件、Timeline 等扩展方向。

**UI 与交互结构**

- “个人地图”是首页，而不是一次性旅行；所有地点都可被多个集合和路线复用。
- 视觉强调地图策展、图标、照片和主题，适合长期收藏。
- 智能路线只是个人地点库上的一个视图，数据资产不随单次旅行消失。

**优势**：把 POI 变成长期可复用的个人知识库。

**风险/局限**：若缺少明确旅行任务，容易成为漂亮但低频的收藏夹。

**对本项目的直接启发**：在 Trip 之外增加 Collection/Place Library，但让“编译成可执行路线”成为更强的转化动作。

来源：[S12]

---

## 5. 主流功能矩阵

|能力|圆周|Wanderlog|TripIt|Tripsy|Tripomatic|Roadtrippers|Mindtrip|Layla|Polarsteps|Placify|本项目|
|---|---|---|---|---|---|---|---|---|---|---|---|
|内容/链接/图片导入|强|部分|邮件|邮件|弱|弱|强|弱|弱|强|当前弱|
|自然语言生成|中|强|弱|中|强|强|强|强|弱|弱|当前强|
|确定性约束/可解释执行|弱-中|中|弱|弱|中|中|中|弱|弱|弱|当前最强|
|行程+地图同屏|强|强|弱|中|强|强|强|中|强|强|已有强|
|路线编辑/优化|强|强|弱|弱|强|强|中|中|弱|强|已有中-强|
|多人协作|强|强|共享|强|强|强|强|中|亲友跟随|规划中|缺失|
|预订/文档|弱|强|最强|强|中|弱|强|强|弱|弱|缺失|
|费用/清单|弱|强|弱|费用强|中|弱|中|弱|弱|弱|缺失|
|旅中实时/离线|中|强|最强|强|强|强|中|中|离线轨迹|弱|缺失|
|足迹/旅行后复盘|强|弱|弱|统计|弱|弱|中|弱|最强|强|缺失|

### 5.1 矩阵解读

- 你的项目在**确定性约束、解释、准备度和路线现实性**上明显比多数消费 App 更深入。
- 最大短板不是“推荐不够多”，而是**输入采集、长期保存、协作、真实预订、旅中与旅行后**。
- 圆周旅迹与 Mindtrip 适合补“入口”；Wanderlog/Tripsy 适合补“Trip OS”；TripIt 适合补“旅中可靠性”；Polarsteps/Placify 适合补“长期留存”。

---

## 6. 主流 UI 模式：Codex 可直接理解的界面描述

### U01 旅行库首页

展示进行中、即将出发、草稿、已结束四类 Trip。卡片至少包含封面、目的地、日期/天数、同行人、准备状态和最近修改。主 CTA 是“新建旅行”，次级入口是“导入攻略/预订”。不要让首页直接变成聊天页。

### U02 统一采集入口

一个入口接受 URL、长文本、图片、截图、PDF、邮件转发结果和手工地点。上传后先进入 Import Inbox，不要直接污染正式行程。每个导入任务显示解析阶段、发现地点数、待确认歧义和失败原因。

### U03 导入审阅队列

左侧原文/截图，右侧结构化候选；每个 POI 显示原始提及、匹配候选、城市、置信度和来源。支持合并重复、改城市、选择正确 POI、标记“仅备注”或“忽略”。确认后才写入 Place Library 或 Trip。

### U04 约束采集与编译

把自然语言转换为可编辑的结构化约束：日期、可用时间、固定事件、必去/可选/排除、节奏、交通方式、预算、同行人需求。界面必须显示“已理解”和“需要确认”，并允许用户逐项修正。

### U05 桌面三栏工作区

建议保留当前“左侧准备度/操作、中间地图、右侧时间线或地点详情”的结构。左栏控制在 280–340px，中间地图自适应，右栏 360–440px。选中地点时右栏切换详情，地图尺寸不应被二次挤压。

### U06 移动端地图 + Bottom Sheet

地图维持空间上下文，底部 Sheet 在 30%/65%/全屏三个高度间切换。Day 标签固定在 Sheet 顶部。地点详情进入全屏或 Sheet 内详情，关闭后恢复原选中项和滚动位置。

### U07 Day 时间线

地点卡显示时间、停留时长、类型、来源、固定状态和操作；地点间插入 Route Segment，显示模式、距离、时间和可信状态。未排程地点作为独立池；拖动跨天时先展示影响预览。

### U08 解释型路线优化

优化按钮不直接静默重排。先显示“预计减少 38 分钟、移动 4 个地点、不会改变 2 个固定事件”，用户确认后应用；结果支持撤销，并在变更日志中记录。

### U09 地点智能详情

详情分为 Identity、Trust、Route Fit、Visit Context、Caveats、Evidence、Actions。除照片与介绍外，必须回答：为什么适合此行程、从前后地点怎么走、信息是否实时、有哪些风险、能否替换/移到未排程。

### U10 Trip Readiness

准备度不是装饰分数。状态至少分 ready/minor-gaps/needs-attention/not-ready，列出首要问题、影响范围、受保护边界、下一步动作和证据。点击问题应定位到具体 Day/地点/路线段。

### U11 AI 调整命令栏

生成后 AI 不再占据整页，而作为“对当前行程应用结构化 patch”的命令栏。示例：把 Day 2 放松一点、下雨时替换户外点、把这个餐厅移到附近的一天。应用前显示影响摘要。

### U12 协作与决策

成员有 owner/editor/commenter/viewer；地点支持点赞/反对/评论；冲突显示“3 人喜欢、1 人无法参加”。AI 可生成折中方案，但最终约束合并与排程由确定性层执行。

### U13 预订与文档钱包

航班、酒店、车票、活动票据进入统一时间线；卡片支持附件、二维码、确认号、取消政策、联系人和提醒。敏感文件独立权限控制，不默认公开给所有同行人。

### U14 旅中模式

默认只显示“现在/下一步/今天剩余”。顶部展示当前状态、下一地点、建议出发时间和异常。低网络环境缓存今日行程、关键地址、票据和地图快照。

### U15 动态修复

当航班延误、天气、闭店或交通异常发生时，系统生成最小修复 patch：删除/移动/替换哪些项、影响多少人、是否破坏固定约束。用户可以接受全部、接受部分或忽略。

### U16 旅行复盘

旅行结束后从已完成地点、照片、备注和路线生成总结。用户可纠正实际到访；输出足迹地图、城市/里程统计、照片故事和可分享卡片。

### 6.17 推荐的全局信息架构

```text
Global
├─ Trips / 旅行库
├─ Places / 地点库
├─ Imports / 导入收件箱
└─ Account / 数据与隐私

Trip Workspace
├─ Overview / 准备度、城市段、同行人、预订摘要
├─ Plan / 地图 + 时间线 + 地点详情
├─ Decisions / 评论、投票、冲突和变更
├─ Bookings / 航班、酒店、车票、活动、附件
├─ Tasks / 清单与责任人
├─ Budget / 费用与分摊
├─ During Trip / 今日与下一步
└─ Recap / 实际到访、足迹和故事
```

### 6.18 推荐的桌面布局

```text
┌──────────────────────────────── Header: 城市/日期/状态/成员/保存 ────────────────────────────────┐
│ Left 300px                    │ Center flexible map                     │ Right 400px          │
│ Trip Readiness                │ Day layers / route segments              │ Day Timeline          │
│ Primary issue                 │ selected stop & neighbors               │ or Place Detail       │
│ Protected boundaries         │ before/after optimization overlay        │ contextual actions    │
│ Completion / AI patch        │ fit route / mode / legend                │ comments/evidence     │
└─────────────────────────────────────────────────────────────────────────────────────────────────┘
```

原则：选中地点时只切换右栏，地图保持稳定；左栏只放“决定下一步”的信息，不堆所有解释。

---

## 7. 推荐产品定位与差异化机制

### 7.1 一句话定位

**把攻略和真实约束编译成可执行旅行计划，并在每次变化时给出最小、可解释、可撤销的修复。**

### 7.2 核心对象不是 Chat，而是 Trip Revision

每次输入、导入、拖拽、优化、协作决策和异常修复都产生一个结构化 patch，最终形成新的 Trip Revision。聊天只是创建 patch 的一种方式。这样可以：

- 保留谁在何时改了什么；
- 计算 change impact；
- 撤销和比较；
- 重放 planner；
- 让协作冲突有明确 base revision；
- 为作品集展示“工程含金量”提供证据。

### 7.3 关键差异化界面

- **Import Review**：多数产品强调一键导入，但很少把识别错误和来源证据做得专业。
- **Trip Readiness**：多数产品只显示路线，本项目显示是否真的能照走。
- **Impact Preview**：多数产品直接重排，本项目先显示变更和边界。
- **Place Trust**：多数产品只有介绍和评分，本项目显示事实来源、时效、冲突和路线适配。
- **Decision Log**：多数协作产品只有共同编辑，本项目可显示多人偏好冲突和折中。

---

## 8. 分阶段路线图

| 阶段 | 优先级 | 目标 |
|---|---|---|
| Phase 0：保护当前优势 | P0 | 完成前端状态拆分、Trip persistence、planner trace、评估 fixtures。目标是让后续开发不再向单文件堆叠，并保证现有确定性边界不倒退。 |
| Phase 1：Source-to-Plan 闭环 | P0/P1 | Universal Import、Import Review、Intent Compiler、Place provenance、Trip Library、只读分享。此阶段形成最有辨识度的“攻略编译器”。 |
| Phase 2：共同决策与真实预订 | P1 | 协作/权限/评论/投票、预订收件箱、日历/PDF/ICS、多城市边界。此阶段从个人工具升级为真实旅行工作区。 |
| Phase 3：旅中执行与动态修复 | P2 | 离线包、During-Trip、实时异常、最小修复、任务与费用。此阶段强调可靠性，不追求花哨生成。 |
| Phase 4：长期地点资产与旅行复盘 | P2/P3 | Place Library、Collections、Footprints、Recap。此阶段解决留存和个人数据资产。 |

### 8.1 建议的优先级排序

**已完成的前置工程**：F-006 路线工作区状态拆分与可维护 UI 架构。

**接下来必须先做**：F-020a、F-001a、F-002/F-003。没有 planner trace、持久化和导入审阅闭环，继续加功能会迅速失控。

**最能形成辨识度**：F-002、F-003、F-004、F-009、F-008。它们把“导入攻略”与“可解释执行”连接起来。

**最能形成产品闭环**：F-010、F-011、F-012、F-015、F-016、F-019。

---

## 9. Codex 实施总则

在把任何一个功能交给 Codex 前，先附上以下规则：

```text
你正在修改 JA0508/ai-travel-planner。
先完整阅读 AGENTS.md、README.md，以及本任务涉及的真实代码。
不要因为本文的建议路径而假设目录存在；先扫描仓库，遵循现有 package convention。

架构边界：
1. LLM 用于理解、候选生成、分类、摘要和解释。
2. 日期时间、路线、硬约束、权限、版本、身份解析、事实时效和 patch 应用必须确定性。
3. 不允许 LLM 直接改最终 itinerary JSON；必须先生成 schema-valid patch，再由 deterministic validator 应用。
4. 不得破坏 fixed events、availability windows、arrival/departure boundaries。
5. 任何实时事实必须带 source、observed_at 和 verification status。

工作方式：
- 先建立 mental model，列出现有入口、数据流、合同和测试。
- 给出最小正确切片，不做无关重构。
- 对前端任务，避免继续扩大 frontend/src/app/page.tsx。
- 对新 domain，保持 API/schema/service 分层，与现有 FastAPI/Pydantic 约定一致。
- 每次 mutation 必须考虑 base revision、幂等、失败恢复和可撤销性。
- 必须提供 loading/empty/partial/error/offline/no-permission/stale-version 状态。
- 必须补充单元、集成和最少一条端到端/fixture 验证。
- 返回：summary、files changed、contract impact、risks、exact verification steps。
```

---

## 10. Codex 可执行功能规格

### F-001 Trip Library、账户与云端持久化

- **优先级**：P0
- **主要层级**：产品基础 / 数据层 / 前端导航
- **目标**：把当前单页、单会话原型升级为可长期保存和恢复的旅行工作区，为协作、导入、预订和复盘提供稳定主键。

#### 用户故事

- 用户能创建、重命名、复制、归档和删除旅行。
- 刷新、换设备或重新登录后，行程、编辑历史和准备状态仍存在。
- 用户能看到即将出发、草稿、已结束旅行，并从最近位置继续。

#### 范围

- Trip CRUD、状态、目的地、日期/天数、封面、所有者、最近修改时间。
- 匿名本地模式可保留，但需要显式“保存到云端”迁移。
- 保存当前 itinerary、trip_intent、planning assumptions、readiness snapshot 和编辑版本。

#### 非目标

- 不在首版实现公开旅行社区。
- 不把所有原始 API 响应无界存储；只存可复现所需的规范化快照。

#### UX 流程

- 新增 `/trips` 旅行库；根路径根据登录与最近旅行跳转。
- 创建旅行允许“空白创建 / 从文字 / 导入内容 / 复制已有旅行”。
- 保存状态显示 Saved / Saving / Offline changes / Conflict。

#### 建议数据合同

```text
Trip{id, owner_id, title, destinations[], start_date?, end_date?, status, cover_asset_id?, latest_revision_id, created_at, updated_at}; TripRevision{id, trip_id, base_revision_id?, source, itinerary_json, intent_json, readiness_json, created_by, created_at}.
```

#### 建议 API

- `POST /trips`
- `GET /trips?status=`
- `GET /trips/{id}`
- `PATCH /trips/{id}`
- `POST /trips/{id}/duplicate`
- `POST /trips/{id}/revisions`
- `POST /trips/{id}/archive`

#### LLM / Deterministic 边界

LLM 不参与存储决策。版本合并、权限和冲突检测必须确定性执行。

#### 必须覆盖的状态

- 首次加载骨架屏
- 空旅行库
- 保存中
- 离线暂存
- 版本冲突
- 无权限
- 归档成功可撤销

#### 验收标准

- Given 用户已生成路线，When 刷新页面，Then 恢复相同 Day、地点顺序、固定约束与 readiness。
- Given 两个客户端基于同一 revision 编辑，When 后提交者保存，Then 返回 409 和冲突摘要，不静默覆盖。
- Given 匿名会话，When 用户登录并选择保存，Then 创建 Trip 并保留本地编辑。

#### 测试

- Trip schema/API 单元测试
- revision optimistic locking 集成测试
- 前端恢复与保存状态 E2E
- 迁移/回滚测试

#### 指标

- 创建后保存成功率
- 恢复成功率
- 冲突率
- 草稿 7 日回访率

#### 与当前仓库的集成提示

- 不要继续扩张 `frontend/src/app/page.tsx`；新增 `frontend/src/features/trips/*`。
- 后端按现有 api/core/schemas/services 约定新增 trip persistence 模块；若目录名不同，先遵循仓库实际 convention。

### F-002 Universal Import：URL、文字、图片、截图与 PDF

- **优先级**：P0
- **主要层级**：采集 / LLM 交互层 / 文档处理
- **目标**：把攻略、聊天、截图和文档中的地点与约束转成可审阅的结构化候选，而不是要求用户重新手输。

#### 用户故事

- 用户粘贴小红书/博客/地图链接，系统提取地点。
- 用户上传截图或 PDF，系统识别地点、日期、营业提示和推荐理由。
- 用户粘贴一段群聊，系统区分建议、确定安排和未决问题。

#### 范围

- 统一 Import Job；支持 text/url/image/pdf 四类首版输入。
- 保留 source artifact、提取片段、候选实体、置信度和解析警告。
- URL 抓取遵守 robots、超时、大小和内容类型限制；失败时保留用户可读原因。

#### 非目标

- 不绕过登录墙或反爬限制。
- 不承诺抓取所有平台；不直接根据低置信度结果修改正式行程。

#### UX 流程

- 入口支持粘贴、拖放、文件选择。
- 进度阶段：queued → fetching → extracting → resolving → review_ready / partial / failed。
- 解析完成后进入 F-003 审阅，不直接生成最终行程。

#### 建议数据合同

```text
ImportJob{id, trip_id?, input_type, status, source_url?, asset_id?, raw_text?, parser_version, error_code?, created_by}; ExtractedMention{id, job_id, span, entity_type, raw_name, city_hint?, time_hint?, recommendation_reason?, confidence}; SourceArtifact{id, mime_type, checksum, storage_uri, privacy_level}.
```

#### 建议 API

- `POST /imports`
- `GET /imports/{id}`
- `POST /imports/{id}/retry`
- `DELETE /imports/{id}`
- `GET /imports/{id}/mentions`

#### LLM / Deterministic 边界

LLM 负责语义提取和分类；文件安全、URL 获取、大小限制、重复检测、POI 解析和写入权限由确定性服务负责。

#### 必须覆盖的状态

- 不支持域名
- 需要登录查看
- 空内容
- 图片模糊
- PDF 超页数
- 部分提取成功
- 重复导入
- 恶意文件拒绝

#### 验收标准

- Given 文本包含 8 个地点和 1 个固定预约，When 导入完成，Then 审阅页显示 8 个地点候选和 1 个 constraint mention，且每项能回看原文。
- Given URL 抓取失败，Then job=partial/failed 并提供“粘贴正文/上传截图”替代动作。
- Given 同一文件重复上传，Then 复用 checksum 结果或提示重复，不重复计费解析。

#### 测试

- 解析 fixture 集：中文攻略、群聊、截图、PDF
- 文件类型/大小/病毒扫描测试
- URL SSRF 防护测试
- LLM 输出 schema validation 与超时 fallback

#### 指标

- 导入完成率
- 每次导入确认的 POI 数
- 低置信度比例
- 从导入到生成路线转化率

#### 与当前仓库的集成提示

- 建议新增 `frontend/src/features/imports/ImportComposer.tsx`、`ImportJobProgress.tsx`。
- 建议新增后端 import orchestration、artifact storage、extractor adapter；LLM prompt 与 deterministic resolver 分离。

### F-003 Import Review Inbox 与 POI 消歧

- **优先级**：P0
- **主要层级**：前端审阅 / POI 解析 / 数据质量
- **目标**：在人机协作中确认“文本里的地点到底是哪一个”，阻止错误地理实体进入调度器。

#### 用户故事

- 用户能看到每个地点来自哪句话/哪张图。
- 同名地点有多个候选时，用户选择正确分店。
- 重复地点可以合并，非地点内容可转成备注。

#### 范围

- mentions 分组：confirmed / needs_review / duplicate / ignored。
- 显示候选 POI 的名称、地址、行政区、距离、类别、provider id 和置信度。
- 批量确认高置信度项，单项处理歧义。

#### 非目标

- 不以 LLM 自信文本代替 provider identity。
- 不在审阅阶段执行全路线优化。

#### UX 流程

- 桌面双栏：左原始内容，右候选清单；点击候选高亮原文和地图点。
- 移动端使用逐卡审阅，顶部进度 N/M。
- 完成按钮显示“将添加 6 个地点、2 条备注、1 个固定事件”。

#### 建议数据合同

```text
ResolvedPlaceCandidate{mention_id, provider, provider_place_id, canonical_name, address, lat, lng, city_code, category, confidence, resolution_reason}; ReviewDecision{mention_id, action, selected_candidate_id?, merge_target_id?, note_text?}.
```

#### 建议 API

- `POST /imports/{id}/resolve`
- `PATCH /imports/{id}/mentions/{mention_id}`
- `POST /imports/{id}/commit`

#### LLM / Deterministic 边界

候选召回可由 provider + 模糊匹配 + LLM rerank 协同；最终 identity、坐标合法性、城市边界和去重规则必须确定性。

#### 必须覆盖的状态

- 无候选
- 跨城市冲突
- 同名分店
- provider 暂不可用
- 坐标缺失
- 候选已被其他协作者修改

#### 验收标准

- When 用户提交审阅，Then 只有 confirmed 项写入 Place Library/Trip。
- When 两个 mention 选择相同 provider_place_id，Then 默认提示合并并保留两个来源证据。
- When 候选城市与 Trip 城市冲突，Then 阻止批量确认并要求显式选择。

#### 测试

- 中文别名/简称/分店消歧 fixture
- 跨城市冲突测试
- 去重与来源合并测试
- 并发审阅版本测试

#### 指标

- 自动确认率
- 人工改选率
- 无候选率
- 后续用户删除错误 POI 的比例

#### 与当前仓库的集成提示

- 复用现有 Place Intelligence 的 trust/evidence 语言；新增 ImportReviewWorkspace 和 resolver service。

### F-004 Trip Intent Compiler 与约束确认台

- **优先级**：P0
- **主要层级**：LLM 交互层 / 确定性合同层
- **目标**：把自然语言、导入内容和表单统一编译为稳定 TripIntentEnvelope，并明确硬约束、软偏好和未决问题。

#### 用户故事

- 用户输入“周六下午到，周日下午三点有预约，不想太赶”，系统形成可编辑结构。
- 用户能知道哪些是硬约束、哪些只是偏好。
- 系统在信息不足时只问最影响路线的问题。

#### 范围

- 字段：目的地、日期/天数、到离边界、可用窗口、固定事件、must/optional/avoid POI、pace、transport、meal、budget、traveler needs。
- 每个字段包含 provenance、confidence、confirmed_by_user。
- 生成 Clarification Queue，按 change impact 排序。

#### 非目标

- LLM 不直接决定最终 Day/时间。
- 不为低影响缺失信息反复阻塞用户。

#### UX 流程

- 自然语言输入后显示“我理解的是”chips/sections。
- 硬约束使用锁图标；软偏好可调强度；冲突用红色显式解释。
- “先生成草案”允许带假设继续，但假设进入 planning_assumptions。

#### 建议数据合同

```text
IntentField<T>{value, kind:hard|soft|assumption, confidence, source_refs[], confirmed}; TripIntentEnvelope{destinations, date_policy, availability_windows, fixed_events, poi_preferences, pace, transport_preferences, budget, travelers, exclusions, assumptions, unresolved_questions}.
```

#### 建议 API

- `POST /trip-intents/parse`
- `PATCH /trip-intents/{id}`
- `POST /trip-intents/{id}/validate`
- `POST /trip-intents/{id}/compile`

#### LLM / Deterministic 边界

LLM 输出必须通过 Pydantic/schema validation；冲突检测、日期计算、窗口重叠、固定事件合法性由确定性 compiler。

#### 必须覆盖的状态

- 解析超时
- 字段冲突
- 日期歧义
- 固定事件越界
- 多城市顺序不清
- 信息不足但可带假设生成

#### 验收标准

- Given “不要太赶”，Then pace=relaxed soft preference，而不是直接删减固定事件。
- Given 固定事件超出旅行日期，Then compiler 返回 blocking issue。
- Given 用户修改结构化字段，Then 后续再生成不得被旧的 LLM 解释覆盖。

#### 测试

- 现有 quick examples 回归
- 日期/中文相对时间测试
- 硬软约束冲突矩阵
- LLM malformed JSON 测试

#### 指标

- 一次解析后修改字段数
- 阻塞问题解决率
- 澄清问题回答率
- 生成后因误解而重做的比例

#### 与当前仓库的集成提示

- 复用现有 parseTripIntent、parsePlanningState、tripFormSync、tripIntentPayload；把 page.tsx 中状态搬到 feature store/hook。

#### 当前实现状态（F-004a.3）

> Integrity repair is in review. PR #20 established the foundation; the following
> describes the repaired branch and must not be read as a merged-completion claim
> until CI and review have accepted it.

- 已建立 `SourceLinkedTripIntentEnvelope` 的 domain-native formal contract：
  destination、date policy、fixed event、place preference、pace、transport、
  meal、budget、traveler need、exclusion 和 typed assumption 均带 metadata、
  authority、confirmation、validation codes、source refs 与 revision ownership。
- 已分离 `semantic_digest` 与 `lineage_digest`。相同语义内容可以跨 revision
  比较，lineage 仍包含 base TripRevision、parent IntentRevision、policy
  version、operation 与 restore 来源。
- parser 结果为 server-only 结果，不接受客户端伪造 parser error；显式记录
  `success`、`empty_input`、`unavailable`、`timeout`、`invalid_output` 和
  `provider_error`。
- reviewed Import commit persists structured candidate-to-artifact/import
  job/mention/review decision/resolution/page/bbox links. Intent compilation
  rehydrates those records rather than parsing string evidence references;
  legacy candidates that cannot be verified remain planner-blocking.
- provenance graph 由结构化 source refs 构建，覆盖 TripCandidate、source
  artifact、import job、mention、review decision、resolution candidate、direct
  user span、LLM proposal、field 和 envelope revision 节点；page/bbox 信息在
  上游 evidence 存在时保留。
- intent compile / edit / clarification / restore 均创建不可变
  IntentRevision；每次写入都显式携带 base TripRevision 与 base
  IntentRevision（首次 compile 可为 null），并在事务内完成 latest parent
  compare-and-append、revision number 分配和 idempotency 记录。
- 持久化 privacy-safe intent compile run metadata，用于回放/evaluation，而不
  保存 raw prompt、raw LLM response 或私有 source text。
- 缺失且没有实际 assumed value 的 `trip.trip_days` 不再标记为
  planner-ready，必须进入 clarification/readiness blocker。
- Intent Confirmation Workspace 可加载 history/detail、编辑 latest revision、
  restore 历史 revision、显示 semantic/lineage digest、semantic compare 和
  provenance evidence nodes；带 import/page identity 的节点会复用现有私有
  Import Review workspace。历史 revision 不能直接编辑，只能 restore 成新
  revision；stale edit 保留 draft，必须显式 reapply 到 latest revision。
- Intent compiler evaluation 现有 62 个 fixtures，按 semantic、provenance、
  parser、revision、concurrency、clarification 分类，并在 CI 下 gate fixture
  数量与 deterministic invariants。
- 当前仍不调用 planner、scheduler、provider lookup，不创建 TripRevision，
  不修改 itinerary。
- 已知限制：provenance graph 不是完整 Planner Trace；部分 page/bbox 证据受
  上游 Import Review evidence 完整度限制；F-004b 才会消费 confirmed
  contract 进入 planner handoff。

### F-005 Explainable Plan Compiler v2

- **优先级**：P0
- **主要层级**：确定性排程 / 解释合同
- **目标**：把已确认意图编译为可复现、可验证、可局部修复的行程，而非一次性文本生成。

#### 用户故事

- 相同输入和 provider snapshot 产生相同结果。
- 每个地点能解释为何放在这一天和这个时段。
- 系统不能为了优化距离移动固定事件。

#### 范围

- 候选筛选、时间块分配、路线成本、开放时间、餐食锚点、到离边界、节奏上限。
- 输出 decision trace 与 rejected candidates reason。
- planner version、provider snapshot version 写入 revision。

#### 非目标

- 首版不求全局最优 TSP/VRP。
- LLM 不输出未经验证的距离、营业时间或票价。

#### UX 流程

- 生成时显示阶段：解析完成、地点确认、路线计算、现实性检查、完成度评估。
- 结果提供“为什么这样排”和“没有加入的地点”。

#### 建议数据合同

```text
PlannerInput{intent, confirmed_places, provider_snapshot, previous_revision?}; PlannerDecision{item_id, day, block, start,end, reasons[], constraints_satisfied[], tradeoffs[]}; RejectedCandidate{place_id, reason_code, detail}.
```

#### 建议 API

- `POST /planner/compile`
- `POST /planner/preview`
- `GET /planner/runs/{id}/trace`

#### LLM / Deterministic 边界

LLM 只生成可读解释草稿；所有 placement、时间、路线和约束结果来自 planner trace。

#### 必须覆盖的状态

- provider 部分缺失
- 无可行解
- 仅能生成 skeleton
- 超时
- 部分路线估算
- 开放时间未知

#### 验收标准

- 固定事件在任何优化/补全后时间不变。
- 每个 scheduled item 至少有 source_type 和 placement_reason。
- 无可行解时返回最小冲突集，而不是虚构计划。

#### 测试

- golden fixture deterministic snapshot
- fixed boundary property tests
- partial provider degradation
- planner version migration

#### 指标

- 可执行状态比例
- 无可行解解释成功率
- 用户应用后手动大改比例
- 平均 route waste

#### 与当前仓库的集成提示

- 沿用现有 scheduler，新增显式 PlannerRun/DecisionTrace；不要为了新功能重写核心排程。

### F-006 路线工作区状态拆分与可维护 UI 架构

- **优先级**：P0
- **主要层级**：前端架构 / UI
- **目标**：解决当前 `frontend/src/app/page.tsx` 约 8,984 行的高耦合风险，使后续功能以模块演进而非继续堆叠。

#### 用户故事

- 开发者能在不理解整页状态机的情况下修改导入、时间线或分享模块。
- 同一 Trip revision 在 desktop/mobile 使用一致 selector 和 mutation。

#### 范围

- 拆分 input flow、generation session、trip workspace、completion、share/export、route edit、collaboration adapters。
- 明确 server state、draft state、selection state、ephemeral UI state。
- 保留现有组件和行为，先做 characterization tests 再移动。

#### 非目标

- 不在同一 PR 重新设计视觉。
- 不引入重量级状态库，除非现有 hooks 已无法保证一致性。

#### UX 流程

- 用户行为不变；只允许修复明显一致性/可访问性问题。

#### 建议数据合同

```text
定义 TripWorkspaceState、TripDraftPatch、SelectionState、AsyncOperationState；所有 mutation 返回 next revision 或 local patch。
```

#### 建议 API

- `无新外部 API；统一使用现有 tripApiClient 和 endpoint config。`

#### LLM / Deterministic 边界

纯工程任务，不调用 LLM。

#### 必须覆盖的状态

- 生成中同时编辑
- 撤销/重做
- 保存失败
- 切换 mobile/desktop breakpoint
- 返回地点详情后的焦点恢复

#### 验收标准

- page.tsx 只保留路由级组合与少量 orchestration。
- 所有现有 typecheck/build/backend tests 通过。
- fixture-result 场景视觉与交互一致。

#### 测试

- 现有 fixture-result 扩展
- hook 单元测试
- Playwright 核心流程
- visual regression

#### 指标

- page.tsx LOC
- 组件平均圈复杂度
- 功能 PR 影响文件数
- 前端回归缺陷数

#### 与当前仓库的集成提示

- 建议目标：`features/planning-input`、`features/trip-workspace`、`features/completion`、`features/sharing`；先由 Codex 扫描依赖图再拆分。

### F-007 高级路线编辑：跨天拖拽、影响预览、版本化撤销

- **优先级**：P1
- **主要层级**：前端交互 / 确定性重算
- **目标**：让用户自由调整，同时保护固定约束并实时理解改动的交通和时间后果。

#### 用户故事

- 用户把地点从 Day 2 拖到 Day 1，系统显示新增交通和时间冲突。
- 用户可以撤销多步编辑或回到已保存版本。
- 移动端可通过“移动到…”替代难用的长距离拖拽。

#### 范围

- 同日排序、跨天移动、移动到未排程、删除、复制、锁定。
- drop preview 返回受影响路线段、预计时间变化、冲突和 readiness delta。
- 操作写入 local patch log，保存时生成 revision。

#### 非目标

- 不每次 pointer move 都调用外部路线 API。
- 不允许拖动破坏固定事件而没有明确冲突。

#### UX 流程

- 拖拽时地图高亮前后邻居；drop zone 显示预计 +25min。
- 冲突时出现选择：取消、移到其他时间、保留但标记不可执行。
- 移动端地点菜单提供“移到 Day/时段”。

#### 建议数据合同

```text
RouteEditPatch{op, item_id, from, to, client_patch_id, base_revision_id}; ImpactPreview{changed_segments[], duration_delta, distance_delta, conflicts[], readiness_delta}.
```

#### 建议 API

- `POST /trips/{id}/edit-previews`
- `POST /trips/{id}/apply-patches`

#### LLM / Deterministic 边界

LLM 不参与拖拽；影响计算、边界保护和 patch 应用确定性。

#### 必须覆盖的状态

- 预览计算中
- 离线估算
- 路线 API 失败
- 冲突
- 并发版本过期
- 撤销栈为空

#### 验收标准

- 移动固定事件时必须被阻止或进入显式解锁流程。
- 每次已提交编辑可在 revision history 中追踪。
- 预览失败时仍允许本地移动，但标记路线待重算。

#### 测试

- drag/drop reducer tests
- fixed item guard
- undo/redo property tests
- impact preview cache tests

#### 指标

- 编辑后撤销率
- 冲突阻止数
- 保存前 route preview 命中率
- 编辑后 readiness 改善比例

#### 与当前仓库的集成提示

- 扩展现有 MobileEditRouteWorkspace state，但优先提取 reducer；复用 neighbor/highlight route context。

### F-008 路线优化 Preview 与可解释应用

- **优先级**：P1
- **主要层级**：优化服务 / UI
- **目标**：提供“减少绕路但不破坏体验”的优化，而不是黑盒重排。

#### 用户故事

- 用户看到优化可节省多少时间、会移动哪些地点。
- 用户可按单日或全行程优化。
- 用户可排除不想移动的地点。

#### 范围

- 锁定 fixed/locked items；生成 1–3 个策略：最快、均衡、少换乘。
- 比较 before/after 路线、时间、步行和 Day 密度。
- 应用为 patch list，支持撤销。

#### 非目标

- 不自动改变必去/排除集合。
- 不以直线距离替代可用的真实路线时间。

#### UX 流程

- 优化侧栏展示 KPI 和变更列表；地图可切换 before/after。
- 每个移动说明原因，例如“与前后地点同片区，减少 32 分钟往返”。

#### 建议数据合同

```text
OptimizationRequest{scope, strategy, locked_item_ids, transport_modes}; OptimizationProposal{patches, metrics_before, metrics_after, tradeoffs, preserved_constraints}.
```

#### 建议 API

- `POST /trips/{id}/optimization-proposals`
- `POST /trips/{id}/optimization-proposals/{proposal_id}/apply`

#### LLM / Deterministic 边界

候选策略和评分确定性；LLM 仅把结构化 tradeoff 改写为用户语言。

#### 必须覆盖的状态

- 无改善
- 仅估算路线
- 部分地点无坐标
- 交通模式不支持
- proposal 过期

#### 验收标准

- 优化结果不得移动 fixed item。
- 若节省不足阈值，返回 no_material_improvement。
- 应用后 readiness 不得从 ready 降到 needs-attention，除非用户显式接受警告。

#### 测试

- optimization invariant tests
- proposal expiry
- before/after metric calculation
- visual diff mode

#### 指标

- proposal 接受率
- 平均节省时长
- 应用后撤销率
- 约束违规数（应为 0）

#### 与当前仓库的集成提示

- 新增 optimization service；前端集成 RouteWorkspaceShell “改线” sheet。

### F-009 Place Intelligence v2：来源、时效与可访问性

- **优先级**：P1
- **主要层级**：地点数据 / 信任 UI
- **目标**：把现有 Trust、Evidence、Route Fit、Caveats 扩展为可审计的地点事实层。

#### 用户故事

- 用户知道营业时间来自哪里、何时更新。
- 用户看到预约、临时闭店、无障碍、儿童/老人适配等风险。
- 同一事实冲突时系统不装作确定。

#### 范围

- Fact model：value、source、observed_at、expires_at、confidence、conflict_group。
- 来源优先级：官方 > 地图 provider > 高可信内容 > LLM 推断。
- 营业、票务、预约、季节、交通入口、无障碍、天气敏感性。

#### 非目标

- 不抓取受限评论全文。
- 不让 LLM 伪造“实时”事实。

#### UX 流程

- Trust Card 显示“实时/近期/可能过期/仅推断”。
- 冲突事实并列展示并提示出发前确认。
- Evidence 支持打开来源，但敏感/受限链接需安全跳转。

#### 建议数据合同

```text
PlaceFact{id, place_id, fact_type, value_json, source_type, source_url?, observed_at, expires_at?, confidence, verification_status}; FactConflict{id, place_id, fact_type, fact_ids[]}.
```

#### 建议 API

- `GET /places/{id}/intelligence`
- `POST /places/{id}/refresh`
- `POST /places/{id}/feedback`

#### LLM / Deterministic 边界

LLM 可摘要多来源；事实标记、过期规则、冲突检测、provider identity 必须确定性。

#### 必须覆盖的状态

- 无实时事实
- 来源冲突
- 来源过期
- 刷新受限
- 用户反馈待验证

#### 验收标准

- 每个“营业/票务/实时”结论必须有 source 和 observed_at。
- 过期事实不得以 confirmed 样式显示。
- 无数据时显示 unknown，不用 LLM 常识补齐。

#### 测试

- fact TTL tests
- source precedence
- conflict rendering
- provider fallback

#### 指标

- 带来源事实覆盖率
- 过期事实点击率
- 用户纠错率
- 因地点事实导致的重规划率

#### 与当前仓库的集成提示

- 扩展现有 `place-intelligence/*` view model 与后端 POI detail contract，保持 fallback 兼容。

### F-010 协作、权限、评论、投票与冲突协调

- **优先级**：P1
- **主要层级**：协作 / 实时 / 权限
- **目标**：支持同行人共同规划，并把偏好分歧转成结构化决策，而不是散落在微信群。

#### 用户故事

- Owner 邀请 Editor、Commenter 或 Viewer。
- 成员对地点点赞、反对、评论并注明原因。
- 系统识别群体冲突并提出不破坏硬约束的折中方案。

#### 范围

- 邀请链接、成员权限、presence、评论、reaction、地点 proposal、审计日志。
- 敏感文档和费用可单独授权。
- 冲突摘要：偏好覆盖、不可参加时段、饮食/无障碍限制。

#### 非目标

- 不做公开社交关注流。
- 不让 AI 自动代表某成员接受折中。

#### UX 流程

- 右上角 avatars + Share；侧栏分 Members、Decisions、Activity。
- 地点卡显示反应计数；点击查看成员和原因。
- 冲突卡提供 2–3 个方案及各成员受益/受损。

#### 建议数据合同

```text
TripMember{trip_id,user_id,role,permissions}; Comment{target_type,target_id,body,mentions}; Reaction{target,user_id,type}; PreferenceClaim{user_id,kind,target,value,priority}; DecisionProposal{id, patches, utility_by_member, fairness_notes}.
```

#### 建议 API

- `POST /trips/{id}/invites`
- `PATCH /trips/{id}/members/{user_id}`
- `POST /comments`
- `POST /reactions`
- `POST /trips/{id}/decision-proposals`

#### LLM / Deterministic 边界

LLM 可总结意见和生成折中候选；权限、成员身份、硬约束合并、公平性指标和 patch 验证确定性。

#### 必须覆盖的状态

- 邀请过期
- 无权限
- 成员同时编辑
- 评论目标已删除
- 冲突无法满足
- 敏感数据不可见

#### 验收标准

- Viewer 无法修改行程。
- 文档权限关闭时，Editor 也不能读取附件 URL。
- AI 方案必须标出无法同时满足的约束，不得静默忽略成员。

#### 测试

- RBAC matrix
- 邀请 token 安全
- concurrent edit
- comment/reaction realtime
- group fairness fixture

#### 指标

- 邀请转化率
- 活跃协作者数
- 冲突解决率
- 评论到决策转化时间

#### 与当前仓库的集成提示

- 建议 WebSocket/SSE 只用于轻量 presence/event；核心写入仍走版本化 API。

### F-011 预订收件箱与旅行文档钱包

- **优先级**：P1
- **主要层级**：组织 / 文档 / 安全
- **目标**：把航班、酒店、车票、活动票据和确认号放入同一旅行，连接规划与真实预订。

#### 用户故事

- 用户转发邮件或上传 PDF/截图，系统识别预订。
- 用户确认后，预订卡进入时间线并成为到离/住宿锚点。
- 旅中能离线打开二维码、地址和确认号。

#### 范围

- 首版支持手工添加、文件上传和通用邮件转发地址；解析后必须确认。
- Booking 类型：flight/train/hotel/car/activity/restaurant/other。
- 附件加密、访问权限、下载审计和敏感信息遮罩。

#### 非目标

- 不首版连接所有邮箱 OAuth。
- 不处理付款或修改订单。

#### UX 流程

- Trip 中新增 Bookings 标签；未确认项目进入 Inbox。
- 卡片顶部显示状态和时间，正文显示地点、确认号、联系人、附件。
- “作为行程锚点”会预览对现有路线的影响。

#### 建议数据合同

```text
Booking{id, trip_id, type, status, start_at,end_at, origin?,destination?, venue_place_id?, confirmation_code_enc?, provider, source_artifact_id, fields_json, verified_by_user}; BookingAttachment{id, booking_id, asset_id, privacy}.
```

#### 建议 API

- `POST /booking-inbox`
- `GET /booking-inbox`
- `POST /bookings`
- `PATCH /bookings/{id}`
- `POST /bookings/{id}/apply-as-anchor`

#### LLM / Deterministic 边界

LLM/OCR 负责字段提取；时间格式、机场/车站身份、重复检测、权限、加密和锚点应用确定性。

#### 必须覆盖的状态

- 解析部分成功
- 重复预订
- 时间区不明
- 敏感字段
- 附件过大
- 离线缓存失败

#### 验收标准

- 未确认 booking 不得自动移动正式行程。
- 确认号在日志/分析中不可明文。
- 应用航班锚点后，第一/最后一天重新计算并生成影响摘要。

#### 测试

- 多种确认邮件/票据 fixture
- PII redaction
- duplicate detection
- anchor impact regression
- download authorization

#### 指标

- 解析确认率
- 字段修改率
- 作为锚点应用率
- 旅中附件打开成功率

#### 与当前仓库的集成提示

- 新增 booking domain；与现有 arrival/departure/stay recommendation 通过明确 adapter 连接。

### F-012 日历、分享、PDF/ICS/地图导出

- **优先级**：P1
- **主要层级**：互操作 / 分享
- **目标**：让计划能离开产品继续使用，并为只读分享和作品展示提供稳定输出。

#### 用户故事

- 用户生成只读分享链接。
- 用户导出 ICS、PDF、JSON 和地图坐标。
- 每次修订后可选择更新同一分享链接或固定到某 revision。

#### 范围

- 公开/私密分享、密码/过期时间、revision pin。
- ICS 每个 scheduled item 或按 Day；PDF 包含时间线、地图快照、关键证据与风险。
- JSON export 保留 schema version；可选 GPX/KML。

#### 非目标

- 不承诺第三方地图保留全部元数据。
- 不在公开分享中泄露私人文档或费用。

#### UX 流程

- RouteWorkspaceShell “导出” sheet 分 Share / Calendar / Document / Data。
- 导出前隐私检查列出将包含的字段。
- 分享页移动端优先、无需登录、只读。

#### 建议数据合同

```text
ShareLink{id,trip_id,revision_id?,token_hash,visibility,expires_at,allowed_sections}; ExportJob{id,type,status,revision_id,options,asset_id?}.
```

#### 建议 API

- `POST /trips/{id}/share-links`
- `DELETE /share-links/{id}`
- `POST /trips/{id}/exports`
- `GET /exports/{id}`

#### LLM / Deterministic 边界

导出确定性；LLM 可生成封面摘要，但不得改变结构化行程。

#### 必须覆盖的状态

- 地图快照失败
- 附件被排除
- 导出处理中
- 链接过期
- revision 已更新

#### 验收标准

- 公开链接默认不含费用、文档、成员邮箱。
- ICS 时间区正确，跨日事件不被截断。
- JSON 包含 schema_version 和 planner_version。

#### 测试

- privacy snapshot
- ICS validator
- PDF visual regression
- expired link authorization

#### 指标

- 分享/导出率
- 分享链接访问率
- ICS 导入成功率
- PDF 生成失败率

#### 与当前仓库的集成提示

- 复用已有 share card feedback；新增服务器端 export renderer，避免浏览器截图不稳定。

### F-013 费用、预算、多币种与分摊

- **优先级**：P2
- **主要层级**：组织 / 财务记录
- **目标**：让用户在计划前估算、旅行中记录、旅行后结算，同时与行程项目关联。

#### 用户故事

- 用户设总预算和分类预算。
- 同行人添加多币种费用并选择付款人/分摊人。
- 地点/预订的预计费用和实际费用可对比。

#### 范围

- estimated vs actual、category、currency、exchange_rate_snapshot、split rules。
- equal/exact/percentage/shares 四种分摊。
- 费用隐私权限和导出 CSV。

#### 非目标

- 不提供投资/支付功能。
- 汇率只作记录，不承诺财务结算准确性。

#### UX 流程

- Budget 标签显示总览、按天/类别/成员。
- 地点卡可显示预计费用但默认不挤占主时间线。
- 结算页显示谁欠谁，并允许标记已结清。

#### 建议数据合同

```text
Budget{trip_id,total?,currency,category_limits}; Expense{id,trip_id,item_id?,booking_id?,amount,currency,base_amount,rate_source,paid_by,occurred_at,category}; ExpenseSplit{expense_id,user_id,amount}.
```

#### 建议 API

- `GET/POST /trips/{id}/expenses`
- `PATCH /expenses/{id}`
- `GET /trips/{id}/settlement`

#### LLM / Deterministic 边界

所有金额、汇率和分摊确定性；LLM 只可从票据建议字段，必须用户确认。

#### 必须覆盖的状态

- 未知汇率
- 分摊不平
- 成员已离开
- 重复票据
- 预算超标

#### 验收标准

- 所有 split 金额之和等于 expense amount（允许最小货币单位舍入）。
- 汇率快照不可因未来更新改变历史记录。
- 无权限成员看不到私密费用。

#### 测试

- currency rounding property tests
- split strategies
- receipt duplicate
- permission matrix

#### 指标

- 费用记录率
- 票据自动填充接受率
- 预算偏差
- 结算完成率

#### 与当前仓库的集成提示

- 独立 expense domain，不与 planner 核心耦合；只通过 item_id/booking_id 关联。

### F-014 Checklist、任务与责任人

- **优先级**：P2
- **主要层级**：协作 / 准备度
- **目标**：把签证、订票、打包、预约等准备工作纳入 Trip Readiness，而不是只评估路线本身。

#### 用户故事

- 用户创建打包清单和待办。
- 任务可分配成员、截止日期和依赖。
- 未完成关键任务会影响准备度。

#### 范围

- 模板：证件、预订、装备、出发前、每日。
- Task priority、owner、due date、blocking、linked booking/place。
- readiness 增加 preparation dimension。

#### 非目标

- 不做通用项目管理软件。

#### UX 流程

- Checklist 标签和 Readiness 侧栏都能看到阻塞任务。
- 完成动效轻量；逾期阻塞任务在旅中模式前置。

#### 建议数据合同

```text
TripTask{id,trip_id,title,status,priority,assignee_id?,due_at?,blocking,linked_entity?}; ChecklistTemplate{id,name,items[]}.
```

#### 建议 API

- `GET/POST /trips/{id}/tasks`
- `PATCH /tasks/{id}`
- `POST /trips/{id}/tasks/from-template`

#### LLM / Deterministic 边界

任务状态确定性；LLM 可根据目的地/预订建议任务，但必须区分 suggestion 与 committed task。

#### 必须覆盖的状态

- 无人负责
- 逾期
- 依赖未完成
- 成员无权限
- 模板重复

#### 验收标准

- blocking task 未完成时 readiness 不得显示完全 ready。
- 建议任务不经确认不得产生通知。
- 完成任务实时更新协作者视图。

#### 测试

- readiness integration
- task dependency
- permission
- template idempotency

#### 指标

- 任务完成率
- 逾期率
- 建议任务采纳率
- 出发前阻塞清零率

#### 与当前仓库的集成提示

- 扩展 TripReadiness ViewModel metrics，但保持路线现实性与准备任务分维度展示。

### F-015 During-Trip Mode 与离线包

- **优先级**：P2
- **主要层级**：旅中执行 / 缓存 / 通知
- **目标**：旅行当天把复杂工作区转换成“现在该做什么”的轻量执行界面。

#### 用户故事

- 用户离线看到今日行程、地址、票据和关键备注。
- 系统显示下一地点和建议出发时间。
- 用户标记到达、完成、跳过或延迟。

#### 范围

- 今日视图、next action、offline pack、关键附件、地图静态/矢量缓存策略、状态回传。
- 到达/完成状态用于复盘，不自动依赖持续定位。

#### 非目标

- 首版不做 turn-by-turn 导航。
- 不默认后台持续追踪位置。

#### UX 流程

- 顶部大卡：当前时间、下一步、出发倒计时；下面只显示今日剩余。
- 一键打开第三方导航。
- 异常/离线状态非常明确。

#### 建议数据合同

```text
OfflinePack{trip_id,revision_id,day,generated_at,expires_at,manifest,assets}; VisitExecution{id,item_id,status,actual_start?,actual_end?,note?}.
```

#### 建议 API

- `POST /trips/{id}/offline-packs`
- `GET /offline-packs/{id}`
- `POST /items/{id}/execution-events`

#### LLM / Deterministic 边界

时间计算和缓存 manifest 确定性；LLM 可生成简短提醒，不可伪造实时位置。

#### 必须覆盖的状态

- 离线包过期
- revision 已更新
- 附件未缓存
- 设备空间不足
- 时区变化

#### 验收标准

- 飞行模式下可打开今日列表、地址、确认号和已缓存附件。
- offline revision 过期时提示差异，不静默覆盖本地状态。
- 标记跳过后不立即自动重排，先生成修复建议。

#### 测试

- service worker/cache tests
- offline E2E
- timezone/DST
- revision mismatch

#### 指标

- 旅中模式打开率
- 离线成功率
- 下一步导航点击率
- 实际完成状态记录率

#### 与当前仓库的集成提示

- Web 端可先做 PWA 离线包；原生持续定位留到后续。

### F-016 Live Disruption Monitor 与最小动态修复

- **优先级**：P2
- **主要层级**：实时数据 / 重规划
- **目标**：在天气、延误、闭店或交通异常时，以最小变更修复路线并清楚解释影响。

#### 用户故事

- 下雨时系统提出室内替换。
- 航班延误后重新裁剪第一天。
- 地点临时闭店时给出附近、同类型且不增大绕行的替代。

#### 范围

- 事件模型、受影响实体匹配、repair policy、proposal、用户确认。
- 优先策略：保护 fixed/booking、最小移动、保持 must-visit、降低群体损失。
- 事件来源和时效必须可见。

#### 非目标

- 不自动取消预订。
- 不基于未经证实社交传言触发高风险修复。

#### UX 流程

- 异常 banner → 影响摘要 → 修复方案 A/B。
- 地图与时间线高亮受影响段；用户可接受部分 patch。

#### 建议数据合同

```text
DisruptionEvent{id,type,severity,source,observed_at,affected_entities,payload}; RepairProposal{id,event_id,base_revision_id,patches,impact,protected_constraints,expires_at}.
```

#### 建议 API

- `POST /disruptions/ingest`
- `GET /trips/{id}/disruptions`
- `POST /trips/{id}/repair-proposals`
- `POST /repair-proposals/{id}/apply`

#### LLM / Deterministic 边界

事件匹配、约束保护、patch 验证确定性；LLM 可生成替代候选和解释，但候选必须经过 POI/路线/营业验证。

#### 必须覆盖的状态

- 数据源冲突
- 事件过期
- 无可行替代
- proposal 过期
- 用户已手工修改

#### 验收标准

- 任何 repair proposal 都显示 source 和 expires_at。
- 应用后固定预订不被移动。
- 无可行替代时返回“缩短/留白”而不是虚构地点。

#### 测试

- weather/flight/closure fixtures
- minimal-change scoring
- stale proposal
- partial apply

#### 指标

- 事件到方案延迟
- 方案接受率
- 平均修改项数
- 修复后 readiness

#### 与当前仓库的集成提示

- 先以模拟/fixture 事件开发，避免一开始被商业实时 API 阻塞。

### F-017 多城市与跨城交通边界

- **优先级**：P2
- **主要层级**：Planner / Domain model
- **目标**：让旅行不再假设单城市，并把跨城段作为一等对象处理。

#### 用户故事

- 用户规划上海-杭州-苏州，系统明确城市顺序和跨城交通。
- 跨城车次/航班成为边界，不和市内 POI 混为普通地点。
- 每个城市可有独立住宿区域和 Day 集合。

#### 范围

- TripLeg、CityStay、IntercityTransfer；日期/时区/到离站。
- 城市内 planner 与跨城 skeleton 分层。
- 跨城段缺预订时可以 placeholder + completion task。

#### 非目标

- 首版不做全球复杂联程出票。

#### UX 流程

- Trip Overview 显示城市段；Day 标签按城市分组。
- 跨城卡片占据时间线完整区间，并影响前后 Day readiness。

#### 建议数据合同

```text
TripLeg{id,from_city,to_city,mode,start_at?,end_at?,booking_id?,status}; CityStay{id,city,day_start,day_end,anchor_place_id?,stay_area?}.
```

#### 建议 API

- `POST /trips/{id}/legs`
- `PATCH /legs/{id}`
- `POST /trips/{id}/compile-multicity`

#### LLM / Deterministic 边界

城市顺序、时间和边界确定性；LLM 只能建议顺序并给出理由，必须经距离/交通可行性验证。

#### 必须覆盖的状态

- 城市顺序歧义
- 交通时长未知
- 跨时区
- 转场过短
- 无住宿锚点

#### 验收标准

- 跨城 transfer 不得被普通 route optimization 拆散。
- 城市内排程只使用该 CityStay 的有效时间窗。
- 缺少跨城信息时 readiness 明确标记。

#### 测试

- multi-city fixtures
- timezone
- boundary trimming
- leg edit impact

#### 指标

- 多城市生成成功率
- 边界问题数
- 转场冲突率
- 用户手动调整城市顺序率

#### 与当前仓库的集成提示

- 在现有 boundary_explanation 之上增加 TripLeg，不要把跨城逻辑硬塞进 ScheduledItem。

### F-018 Place Library、Collections 与 Saved Pins 导入

- **优先级**：P2
- **主要层级**：长期资产 / 发现
- **目标**：让用户收藏的地点跨旅行复用，并把个人品味变成后续推荐上下文。

#### 用户故事

- 用户建立“上海咖啡”“想去的美术馆”等集合。
- 用户从地图保存点或过去旅行导入。
- 创建新 Trip 时从个人地点库选取候选。

#### 范围

- Place identity 与 user-specific note/tags 分离。
- Collection 多对多、来源、访问状态、评分、照片。
- 导入 Google Maps/CSV/GeoJSON 可作为后续 adapter。

#### 非目标

- 不首版做公开达人社区。
- 不复制第三方评论内容。

#### UX 流程

- 全局 Places 页面使用地图/列表切换；Trip 内“从收藏加入”。
- 地点显示 Been / Want to go / Avoid 和最近用于哪次旅行。

#### 建议数据合同

```text
UserPlace{id,user_id,canonical_place_id,status,note,tags,rating,source_refs}; Collection{id,owner_id,title,visibility}; CollectionItem{collection_id,user_place_id,order}.
```

#### 建议 API

- `GET/POST /places/library`
- `GET/POST /collections`
- `POST /collections/{id}/imports`
- `POST /trips/{id}/candidates/from-collection`

#### LLM / Deterministic 边界

LLM 可做标签/主题建议；身份、所有权、重复合并确定性。

#### 必须覆盖的状态

- 导入重复
- 地点已关闭
- 坐标变化
- 第三方 token 失效
- 私密集合

#### 验收标准

- 同一 canonical place 可属于多个集合但只有一个 user-place identity。
- 加入 Trip 时复制引用而不是破坏集合。
- 已关闭地点标记风险，不自动删除历史记录。

#### 测试

- dedup
- collection permissions
- import adapter
- closed place handling

#### 指标

- 收藏到行程转化率
- 集合复用率
- 重复率
- 长期回访率

#### 与当前仓库的集成提示

- 与 F-003 共用 canonical place resolver；Trip item 只引用 canonical/user place。

### F-019 Trip Recap、Footprints 与实际行程

- **优先级**：P3
- **主要层级**：旅行后 / 留存
- **目标**：把执行结果转成可回顾、可分享、可继续积累的旅行资产。

#### 用户故事

- 用户确认实际去了哪些地点并添加照片/备注。
- 系统生成足迹地图、统计和旅行故事草稿。
- 用户能把未去地点保留到收藏。

#### 范围

- actual visit 状态、照片绑定、轻量路线、统计、分享卡。
- AI 总结必须引用用户记录，不虚构体验。
- 旅行结束后自动提出 recap，用户可跳过。

#### 非目标

- 首版不做后台 GPS 自动轨迹。
- 不默认公开照片和位置。

#### UX 流程

- 结束页比较 Planned vs Actual；一键将跳过地点移回 Want to go。
- Recap 编辑器采用地图 + 大图 + 短文，不使用规划期复杂控制。

#### 建议数据合同

```text
ActualVisit{trip_id,item_id,status,actual_at?,note,asset_ids[]}; TripRecap{id,trip_id,stats_json,story_blocks,visibility}.
```

#### 建议 API

- `POST /trips/{id}/actual-visits`
- `POST /trips/{id}/recap/generate`
- `PATCH /recaps/{id}`
- `POST /recaps/{id}/share`

#### LLM / Deterministic 边界

统计确定性；LLM 只基于 ActualVisit/notes/assets 生成可编辑叙事，禁止补写未发生经历。

#### 必须覆盖的状态

- 无执行记录
- 照片权限缺失
- AI 总结证据不足
- 分享隐私检查

#### 验收标准

- 未标记完成的地点不得写成“我们去了”。
- 所有统计可追溯到 actual visits。
- recap 默认 private。

#### 测试

- planned-vs-actual
- evidence-grounded generation
- privacy export
- asset missing

#### 指标

- 旅行后 7 日 recap 创建率
- 分享率
- 跳过地点转收藏率
- 30 日回访率

#### 与当前仓库的集成提示

- 复用 Place Library 和 ShareLink；与 planner 保持只读关系。

### F-020 可观测性、评估基准与产品分析

- **优先级**：P0
- **主要层级**：质量 / 研究 / 工程
- **目标**：证明产品不是“看起来能跑”，而是在约束满足、可行性、解释和用户修正成本上持续提升。

#### 用户故事

- 开发者能重放一次生成并看到每层输入输出。
- 每次版本能在固定 fixture 上比较可行性和回归。
- 产品团队知道用户在哪一步放弃或大量手改。

#### 范围

- request_id、planner_run_id、revision_id、provider snapshot、LLM prompt version、latency/cost、error taxonomy。
- 离线 benchmark：固定约束、路线效率、开放时间、可执行性、个性化覆盖、多人公平。
- 前端事件：导入、确认、生成、修复、撤销、分享。

#### 非目标

- 不记录原始敏感文本到普通日志。
- 不以单一 LLM judge 作为唯一质量指标。

#### UX 流程

- 开发环境提供 Inspector；生产只暴露用户可理解的“依据/边界”。
- 错误页面显示 request id，便于反馈。

#### 建议数据合同

```text
PlanningRun{id,trip_id?,request_id,planner_version,prompt_versions,provider_snapshot_ids,status,metrics,trace_uri}; EvaluationCase{id,input,expected_invariants}; ProductEvent{event_name,anonymous_user_id?,trip_id?,properties_redacted}.
```

#### 建议 API

- `GET /readiness（已有，扩展）`
- `GET /debug/planner-runs/{id}（dev/admin）`
- `POST /analytics/events`
- `CLI benchmark command`

#### LLM / Deterministic 边界

评估指标和 invariant 确定性；LLM judge 仅作为辅助维度，结果要标 model/version。

#### 必须覆盖的状态

- 日志降采样
- provider 不可重放
- 隐私字段屏蔽
- benchmark flaky
- LLM judge 不一致

#### 验收标准

- 每个生成响应带 request_id/planner_run_id。
- CI 运行关键 deterministic fixtures。
- 日志不含确认号、附件正文或完整私人行程文本。

#### 测试

- PII log audit
- trace replay
- benchmark regression threshold
- analytics schema validation

#### 指标

- constraint violation rate
- manual edit distance
- planner failure taxonomy
- p95 latency/cost
- readiness improvement after repair

#### 与当前仓库的集成提示

- 在现有 X-Request-ID、X-Process-Time-Ms 和 fixture QA 基础上扩展，不另起一套孤立观测系统。

---

## 11. 推荐领域模型

```text
User
 ├─ TripMember ───────────────┐
 ├─ UserPlace ─ Collection    │
 └─ ImportJob                 │
                              ▼
Trip ── TripRevision ── TripIntentEnvelope
 │          │                 │
 │          ├─ Itinerary ─ ScheduledItem ─ RouteSegment
 │          ├─ PlannerRun ─ DecisionTrace
 │          ├─ ReadinessSnapshot
 │          └─ PatchLog
 │
 ├─ TripLeg / CityStay
 ├─ Booking ─ Attachment
 ├─ Task
 ├─ Expense ─ ExpenseSplit
 ├─ Comment / Reaction / DecisionProposal
 ├─ DisruptionEvent / RepairProposal
 └─ ActualVisit / TripRecap

CanonicalPlace
 ├─ PlaceFact / FactConflict
 ├─ SourceReference
 └─ ProviderIdentity
```

### 11.1 关键建模原则

- `CanonicalPlace` 与 `ScheduledItem` 分离：地点身份不应因为被放入某一天而复制成多个不一致对象。
- `TripRevision` 是保存和协作的单位，`PatchLog` 是修改的单位。
- `Booking`、`TripLeg`、`FixedEvent` 是边界对象，不应伪装成普通景点。
- `PlaceFact` 必须支持多来源冲突和过期。
- `ActualVisit` 与 `ScheduledItem` 分离，避免计划被旅行后事实反向污染。

---

## 12. 最推荐的首个大版本：Import-to-Executable v1

这是最适合作为下一阶段作品集主线的组合，不需要先完成所有 F-001～F-020：

1. F-006 前端拆分与 characterization fixtures（已完成）。
2. F-020a Planner Trace and Deterministic Evaluation。
3. F-001a Trip + TripRevision Persistence。
4. F-002 Universal Import。
5. F-003 Import Review。
6. F-004 Intent Compiler。
7. F-005 Planner trace。
8. F-009 Place source/freshness。
9. F-008 Explainable optimization preview。
10. F-012 只读分享和 PDF。
11. F-020 benchmark + telemetry。

完成后，演示路径应为：

```text
复制一篇攻略/上传截图
→ 系统识别 12 个地点和 2 个时间约束
→ 用户在 Review Inbox 纠正 2 个同名地点
→ Intent Compiler 显示硬约束、节奏与假设
→ 生成可执行路线
→ Readiness 指出 Day 2 晚餐和离开边界风险
→ 用户应用两个最小修复 patch
→ 优化 Preview 显示减少 46 分钟且不移动固定预约
→ 导出分享页/PDF，所有地点显示来源与时效
```

这条演示链路比“输入杭州三天，AI 给我一张卡片列表”具有显著更高的技术和产品分辨度。

---

## 13. 风险与边界

- **数据授权与抓取**：只抓取公开、允许访问的内容；保存原始内容前明确隐私和版权策略。
- **位置和旅行隐私**：默认私密；分享、协作、文档和费用采用最小权限。
- **实时事实责任**：显示来源与更新时间；高风险信息提醒用户向官方确认。
- **LLM 成本与稳定性**：Import/Intent/Explanation 分离缓存；每层有超时和 schema fallback。
- **地图供应商锁定**：抽象 provider identity 和 route adapter；当前高德实现可保留，但数据模型不应写死。
- **范围失控**：预订、费用、足迹都应作为独立 domain 接入，不重写 planner。

---

## 14. 参考来源

- **[S01] JA0508/ai-travel-planner** — 当前项目仓库：README、AGENTS.md、frontend/src/app/page.tsx、RouteWorkspaceShell、TripReadiness、Place Intelligence 等。 访问：https://github.com/JA0508/ai-travel-planner
- **[S02] 圆周旅迹官网** — 产品入口与官方定位；结合公开页面和产品截图核实内容导入、地图行程、协作、足迹等能力。 访问：https://www.pitravel.cn/
- **[S03] 圆周旅迹产品介绍与公开版本说明** — 用于补充链接/文字/图片解析、路线编辑、多人协作、足迹与旅途记录等细节；属于二级来源，文档中已明确标注。 访问：https://www.sohu.com/a/913861373_121798711
- **[S04] Wanderlog Official** — 行程+地图、路线优化、协作、预订导入、预算分摊、清单、离线与导出。 访问：https://wanderlog.com/
- **[S05] TripIt / TripIt Pro Official** — 邮件转发自动生成行程、航班状态、替代航班、机场地图、登机口、行李转盘、风险提醒、证件提醒。 访问：https://www.tripit.com/web/pro
- **[S06] Roadtrippers Official** — 自驾路线、沿途 POI、Autopilot、车辆档案、油费估算、协作、离线地图、实时交通、RV 导航。 访问：https://roadtrippers.com/
- **[S07] Tripomatic Official** — 按天拖拽、智能路线、多交通方式、离线、PDF/GPX/KML、费用、协作与账户复用。 访问：https://tripomatic.com/en
- **[S08] Tripsy Official** — 预订邮件导入、航班实时信息、日历同步、细粒度访客权限、多币种费用、文档和旅行统计。 访问：https://tripsy.app/
- **[S09] Polarsteps Official** — 计划、自动轨迹、照片故事、亲友关注、旅行统计、Reel 与旅行书。 访问：https://www.polarsteps.com/
- **[S10] Mindtrip Official** — 对话式规划、Start Anywhere、多模态内容导入、收藏集、群组协作、预订凭证整理和附近活动。 访问：https://mindtrip.ai/
- **[S11] Layla Official** — 对话式行程、预算/风格个性化、多城市路线、航班酒店活动聚合和可预订转化。 访问：https://layla.ai/
- **[S12] Placify（原 exping）Official** — 跨 App 收藏地点、个人地图、集合、智能路线、Flyover、回忆、隐私优先与本地/iCloud 同步。 访问：https://placify.app/
- **[S13] ITINERA GitHub / EMNLP 2024** — LLM 请求分解 + POI 候选选择 + 聚类感知空间优化 + 行程生成。 访问：https://github.com/YihongT/ITINERA
- **[S14] OpenTripPlanner GitHub** — GTFS + OpenStreetMap 的多模式公共交通规划，支持实时更新和服务中断。 访问：https://github.com/opentripplanner/OpenTripPlanner
- **[S15] AWS Personalized Travel Itinerary Planner** — 用户画像、兴趣和预订信息进入提示工程与个性化行程生成。 访问：https://github.com/aws-samples/personalized-travel-itinerary-planner
- **[S16] TravelPlanner Benchmark** — 真实世界旅行规划、多工具和多约束评估；论文报告 GPT-4 成功率仅 0.6%。 访问：https://arxiv.org/abs/2402.01622
- **[S17] TripTailor Benchmark** — 超过 50 万 POI、近 4,000 条真实行程；评估可行性、合理性和个性化。 访问：https://arxiv.org/abs/2508.01432
- **[S18] Flex-TravelPlanner** — 多轮新增约束与优先级冲突，证明动态重规划不能只依赖单次生成。 访问：https://arxiv.org/abs/2506.04649
- **[S19] GroupTravelBench** — 多人偏好收集、冲突协调、公平性与群组效用；2026 年研究。 访问：https://arxiv.org/abs/2605.25200

> 说明：产品功能会持续变化。本文以 2026-07-12 可访问的官方页面、仓库与论文为准；圆周旅迹部分细节因官网正文较少，结合公开产品介绍和截图交叉核对。

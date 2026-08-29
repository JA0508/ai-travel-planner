# 实施计划：Import 全形式 Release 闭环与能力包管理

## 目标

把当前已具备的 text、URL、image、PDF 导入能力，收敛为一次可验证、可降级、可发布的
`Import 全形式 Release`。本轮不新增“导入即生成行程”的捷径；四类输入仍必须走
`SourceArtifact → ImportJob → Review → TripCandidate`，并在显式 review commit 后才能进入
后续 Intent / Planner 主链。

这里的“能力包管理”指一个**服务端权威的 Import Capability Pack**：它向前端和发布验证
明确公布每种输入的可用性、当前运行环境是否满足其处理前提、不可用原因及安全边界。它
不是用户权限系统，不替代 Trip capability cookie，也不暴露密钥、原始内容或主机细节。

## 不变边界

- 复用现有 `/trips/{trip_id}/imports/*`、artifact、inspection、extraction、review 与 commit
  领域模型；不得创建第二套 ImportJob、TripCandidate 或 artifact 存储链。
- LLM 只可提出提取/解释；canonical identity、artifact 检查、URL 安全、页面提取、review
  version、idempotency 和 TripCandidate commit 仍由确定性层负责。
- capability pack 只能表达当前可执行条件和降级原因，不把“可导入”误写成“已验证/可执行”。
- URL 不绕过 robots、登录墙、SSRF/DNS 规则或 TLS 规则；二进制文件仍需 quarantine-first。
- import commit 不得创建 `TripRevision`、运行 planner 或修改 itinerary。
- 所有 batch 只在其范围内工作；前一 batch 的提交是后一 batch 的唯一基线。

## Release 能力矩阵

| 输入形式 | 现有安全入口 | Release 必须证明的结果 | 不可用时的用户语义 |
|---|---|---|---|
| Text | `POST …/imports/text` | 私有 artifact、mentions、review decision、idempotent commit | 输入校验错误；不创建半成品 itinerary |
| URL | `POST …/imports/url` | URL policy / robots / bounded fetch / derived text / review | 显示可读失败原因，建议粘贴文字 |
| Image | `POST …/imports/artifacts` + inspection + extraction | metadata-stripped derivative、OCR capability 或明确 unavailable、review | 保持 quarantined/partial，不伪装完成 |
| PDF | `POST …/imports/artifacts` + inspection + page extraction | native-text/OCR 分页证据、retry lineage、review | 加密/拒绝/部分页失败均保留明确状态 |

## Batch 顺序与依赖

```text
Batch 00 Release contract & baseline
  → Batch 01 Server capability pack contract
    → Batch 02 Frontend capability-aware intake
      → Batch 03 Review-to-candidate closure across all forms
        → Batch 04 Four-form API/evaluation release gate
          → Batch 05 Browser release gate, documentation, final release record
```

每个 Batch 是单独的 Codex 对话、单独提交，并且前一个 Batch 完成且工作树干净后才启动下一个。
调度器在当前 Batch 活跃期间每 30 分钟检查一次；收到完成状态则立即启动后续 Batch，不人为等待。

---

## Batch 00：Release Contract、能力矩阵与基线（文档/测试边界）

**目的**：把 release 范围、既有接口、四类输入的成功/降级/禁止语义和验证命令固定下来，
以防后续实现把安全边界或入口行为改散。

**范围**：只新增或更新 release contract、测试/fixture 清单和 CI 入口说明；不得调整生产
业务逻辑、API contract 或 UI。

**重点文件**：

- `docs/product/IMPORT_FULL_FORMAT_RELEASE.md`（新）
- `docs/architecture/IMPORT_CAPABILITY_PACK_CONTRACT.md`（新）
- `backend/tests/` 中现有 import 相关测试的 release manifest/fixture 索引（仅在确有必要时）
- `.github/workflows/`（仅当已有 CI 入口需要文档化，不能新建无效 workflow）

**完成标准**：

- 明确四种输入的入口、阶段、失败/降级状态、数据保留和禁止行为。
- 明确 capability pack 的最小公开字段与“绝不公开”的字段。
- 列出后续 Batch 的稳定 API 与现有测试/命令，不凭空宣称已存在的 release gate。
- 文档链接到 ADR-0007～0011 与 current phase；不修改 `PRODUCT_DIRECTION.md`。
- 文档和测试清单通过格式/相关 focused test；提交后工作树干净。

**依赖**：无。

---

## Batch 01：服务端 Import Capability Pack 合同

**目的**：建立服务端权威、隐私安全的 capability snapshot，使 UI 与 release tests 可统一读取
text / URL / image / PDF 的可用性、处理阶段和降级原因。

**范围**：新增最小 Pydantic schema、纯组装器/服务、只读 API endpoint 与 contract tests。复用
已有 OCR/renderer/inspector/provider capability 检测；不重写 upload、URL fetch 或 extraction。

**重点文件**：

- `backend/app/imports/` 下新增 focused capability-pack 模块
- `backend/app/imports/domain.py` 或既有 schema owner（仅在确需公开 schema 时）
- `backend/app/api/routes/trips.py`（添加窄只读 endpoint）
- `backend/tests/test_*import*.py`（schema、degraded、secret-redaction、route contract）
- 如真实 contract 变化，更新 Batch 00 文档

**完成标准**：

- endpoint 以 Trip capability 访问控制，未授权不能读取 snapshot。
- 每个输入形式返回 `available / degraded / unavailable` 等稳定、可解释状态及安全的 reason codes。
- 缺失 OCR/rendering capability 时 image/PDF 不能被标记为 ready；text/URL 不受无关二进制能力影响。
- 不返回 API keys、原始路径、cookie、完整环境变量、私有 source 内容或内部网络细节。
- 最小 API/服务测试覆盖成功、降级、未授权与 redaction。

**依赖**：Batch 00。

---

## Batch 02：前端 Capability-Aware Unified Import Intake

**目的**：让现有 Import Review workspace 在导入前就如实呈现可用输入形式与限制，并把文字、
URL、图片、PDF 收敛为同一个可理解的 intake 状态机，而不假装所有能力都可用。

**范围**：复用 `frontend/src/features/imports` 的 API client、state、BinaryImportComposer 和
ImportReviewWorkspace；增加类型化 capability client/state/view-model 与窄 UI 入口。不能重造
review UI 或复制二进制流程。

**重点文件**：

- `frontend/src/features/imports/importTypes.ts`
- `frontend/src/features/imports/importApi.ts`
- `frontend/src/features/imports/importState.ts` / `importViewModel.ts`
- `frontend/src/features/imports/ImportReviewWorkspace.tsx` 与必要的 focused composer component
- 对应 unit/smoke/security tests

**完成标准**：

- 页面加载 capability snapshot，加载/错误/降级三态明确且不阻塞已安全可用的形式。
- 不可用的 form 禁止提交，并显示服务端 reason code 的用户可理解文案；不把“部分可用”显示为成功。
- API capability/上传/commit 状态均只由一个 state owner 管理；不向 localStorage 写 capability 或原始文件内容。
- text、URL、image、PDF 均沿现有端点发起，前端不判断或伪造 inspection/extraction 成功。
- focused unit/smoke tests 覆盖四种 form、disabled 状态与无 secret 泄漏。

**依赖**：Batch 01。

---

## Batch 03：全形式 Review → Candidate 闭环一致性

**目的**：补齐或修复四种输入从获取/提取结果进入 Import Review、可做显式 decision、再 idempotent
commit 到现有 TripCandidate 的共同闭环；重点是消除 form-specific 的状态断裂，不扩大到 Intent 或 planner。

**范围**：以现有 service/repository 和 ImportReviewWorkspace 为基础，针对 release matrix 暴露的真实
断点做最小修复。若四条路径已满足合同，则只补测试/文档，不新增业务行为。

**重点文件**：

- `backend/app/imports/service.py` 及其现有 domain/repository helpers（仅必要部分）
- `frontend/src/features/imports/ImportReviewWorkspace.tsx` 与 document evidence view-model（仅必要部分）
- `backend/tests/test_text_import_foundation.py`、`test_url_import_security.py`、`test_binary_artifact_import.py`
- `frontend/src/features/imports/*test.ts*`

**完成标准**：

- 每种可完成输入都能抵达 review-ready 或明确 partial/failed；不会跳过 inspection、source provenance 或 review decision。
- 重复 commit、stale review version、unresolved/ambiguous mention 仍按原有确定性规则拒绝或 replay，且不创建重复 candidate。
- image/PDF 的 page/preview/evidence 仍保持私有访问、sanitized preview 与 generation/retry lineage。
- commit 的可见产物限定为现有 TripCandidate / reviewed context；断言没有 TripRevision 或 itinerary mutation。
- 以发现的真实断点为准实现最小修复并补回归测试。

**依赖**：Batch 02。

---

## Batch 04：四形式 API 与评测 Release Gate

**目的**：让 release 不再依赖“单项测试各自通过”，而能以可重复 fixture/evaluation 证明四种输入的
成功、降级与安全拒绝语义，形成 CI 可执行门。

**范围**：扩展现有 import evaluation / API tests / fixture manifest；不引入真实网络、真实用户文件、
密钥或基于时间的脆弱断言。

**重点文件**：

- `backend/tools/run_import_evaluation.py`
- `backend/tests/fixtures/` 下既有 import/document fixture manifest
- `backend/tests/test_*import*.py`
- `.github/workflows/` 中已有测试调用点（仅在必要时）
- release 文档中的准确命令与覆盖矩阵

**完成标准**：

- gate 覆盖 text、URL、image、PDF 的至少一条正常闭环，以及 URL 安全拒绝、二进制拒绝/partial、
  OCR unavailable 等明确降级路径。
- 所有 fixture 为本地、可审计、无真实个人资料/外部请求；输出不记录原始导入内容、cookie 或 secrets。
- gate 失败时清楚标明 input form、stage 与稳定 reason code。
- 现有 import 与 frontend focused tests 不回归；命令可在干净环境运行。

**依赖**：Batch 03。

---

## Batch 05：浏览器 Release Gate、Runbook 与发布记录

**目的**：完成发布前的端到端真实 UI 验证、可操作 runbook 与当前 phase 记录。此 Batch 只修复自身发现的
阻断 release 的小问题；较大产品改动必须记录为后续任务，不能夹带。

**范围**：复用现有 Playwright/e2e fixture app；运行四形式的浏览器最小流程，检查 privacy headers、
capability degradation 和 commit 边界，产出 release record。只在所有矩阵项真正满足后更新 phase 状态。

**重点文件**：

- `frontend/*playwright*.config.ts` 与既有 e2e specs（仅必要新增）
- `docs/product/IMPORT_FULL_FORMAT_RELEASE.md`
- `docs/product/CURRENT_PHASE.md`（仅完成后更新）
- `docs/architecture/` 下 release record（新，日期化且不含私有样本）

**完成标准**：

- 以 fixture 环境跑通四种形式的浏览器 smoke 或明确记录受运行时 capability 限制的预期降级。
- 验证页面不渲染原始 HTML/PDF、不泄漏 artifact path/capability，且导入不直接修改 itinerary。
- runbook 包含启动、环境前提、验证命令、失败排查、回滚/禁用某 form 的办法。
- `CURRENT_PHASE.md` 只记录已验证事实；未完成项列为 known limitation，不伪称 release 完成。
- 完成 review、全套相关 tests、`git diff --check`，单一语义提交并保持工作树干净。

**依赖**：Batch 04。

## 全局验证与调度规则

每个 Batch 都必须：

1. 先读当前 `AGENTS.md`、本计划对应 Batch、相关模块和测试；执行 `git status --short`。
2. 保留无关改动；只提交本 Batch 的文件。出现与并行遗留改动重叠时停止并汇报，不覆盖。
3. 先做 focused tests，再运行该 Batch 实际影响的 backend/frontend checks；最后运行 `git diff --check`。
4. 每个 Batch 的最后、且仅最后可启动一次双子 reviewer；修复其指出的当前 Batch 问题。
5. 提交前确认工作树干净，使用语义化 commit；不 push、不改密钥、不删除历史 artifact。
6. 若阻断连续两次状态检查仍无可安全推进的操作，只汇报阻断事实，由调度器创建新对话处理。

## 风险与缓解

| 风险 | 影响 | 缓解 |
|---|---|---|
| 把能力状态误作真实性或授权状态 | 高 | schema 明确是 runtime availability；保留 Trip capability 与 review 语义 |
| UI 重做导致四条成熟 import pipeline 重新分叉 | 高 | 复用 importApi / importState / ReviewWorkspace；Batch 02 仅做窄状态整合 |
| OCR/renderer 在本地/CI 能力不同 | 中 | capability pack + deterministic fixture degradation；不把本地缺失当作成功 |
| URL 或二进制 release 测试引入外网/真实资料 | 高 | 本地 fixture、stub transport、无 secret / PII 的 artifact |
| Release 汇总掩盖 partial/failed 页面 | 高 | release matrix 单列降级与拒绝路径；partial 永不渲染为 ready |

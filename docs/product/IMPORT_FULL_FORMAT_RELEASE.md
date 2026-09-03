# Import 全形式 Release 合同

## 状态与范围

本文是 Import 全形式 Release 的合同、验证矩阵与操作 runbook。当前本地
release-gate evidence 已覆盖 API/evaluation；Batch 05 新增浏览器 fixture gate
与重跑步骤，但本次 Codex 沙箱重跑未取得浏览器通过结果。它不是外部发布、
部署或生产环境可用性的声明。2026-09-03 的 evidence、已知限制与重跑步骤见
[Release Record（2026-09-03）](../architecture/IMPORT_FULL_FORMAT_RELEASE_RECORD_2026-09-03.md)。

本 release 仍遵守唯一的导入链：

```text
输入来源 → SourceArtifact → ImportJob → Review → TripCandidate
```

每一种形式都必须经显式 review decision 后，才可使用既有 commit endpoint
创建或复用 `TripCandidate`。commit 不创建 `TripRevision`、不运行 planner、
不修改 itinerary，也不绕过 candidate admission。

## 已有稳定入口与共同边界

所有写入入口要求当前 trip capability、有效 Origin 与
`X-Idempotency-Key`。读取仍通过 trip capability 保护；私有 source、
sanitized preview 与 document page preview 使用 `private, no-store`，并带有
`X-Content-Type-Options: nosniff`。

| 用途 | 现有 endpoint | 说明 |
| --- | --- | --- |
| 文本创建 | `POST /trips/{trip_id}/imports/text` | 创建文本 artifact 与 import job。 |
| URL 创建 | `POST /trips/{trip_id}/imports/url` | 在服务器 URL policy、robots 与 bounded fetch 后创建 provenance。 |
| 图片/PDF 上传 | `POST /trips/{trip_id}/imports/artifacts` | multipart upload；`declared_kind` 不是真实类型的信任来源。 |
| review 读取 | `GET /trips/{trip_id}/imports/{import_job_id}` | 返回 import job、mentions、resolution 与 review 状态。 |
| artifact 文本读取 | `GET /trips/{trip_id}/imports/{import_job_id}/artifact` | 仅供可文本化 artifact；原始二进制不 inline。 |
| 检查与预览 | `GET …/inspection`、`GET …/sanitized-image` | 检查结果与 metadata-stripped image derivative；原始二进制保持私有。 |
| 文档提取/证据 | `POST …/extract-document`、`GET …/document-extraction`、`GET …/document-extraction/pages/{page_number}/preview` | 提取只从 `artifact_ready` 二进制开始；页面 retry 产生新 generation。 |
| review decision | `POST …/mentions/{mention_id}/decisions` | 基于 `base_review_version` 的 append-only decision。 |
| review commit | `POST …/commit` | 仅 confirmed places 创建或复用 `TripCandidate`。 |

### Batch 01：Import Capability Pack

`GET /trips/{trip_id}/imports/capabilities` 是受现有 trip capability cookie 保护的只读
runtime snapshot。它固定返回 text、URL、image、PDF 四种 form，并对每种 form 返回
`available`、`degraded` 或 `unavailable`、稳定 reason code、公开 processing stage 与
safety boundary code。没有有效 capability 时返回既有 `403 trip_access_denied`，且不泄漏
snapshot 内容。

snapshot 不能代替任何写入路径的输入验证、URL/binary 安全边界、review version 或
idempotency；它不创建 artifact、job、review decision、candidate 或 revision，也不触发
fetch、upload 或 extraction。完整字段与 redaction 边界见
[Import Capability Pack 合同](../architecture/IMPORT_CAPABILITY_PACK_CONTRACT.md)。

上表中的省略号只代表同一个 `/trips/{trip_id}/imports/{import_job_id}`
前缀，不是新增路由。Batch 00 不改变这些 API contract。

## 四种输入的 release 语义

| 输入 | 入口与阶段 | 可接受结果 | 降级/失败与数据保留 | 禁止行为 |
| --- | --- | --- | --- | --- |
| Text | `imports/text` → extract mentions → resolve → `review_ready`/`partial` → review | 私有 `SourceArtifact`、可追溯 mention spans、显式 decision、幂等 commit。 | 空、无效编码、超限等输入错误不产生 itinerary；无法完全解析时保持 `partial`/明确 resolution state。已创建 artifact/job 仍是私有证据。 | 不把 prompt-like/XSS source 当指令；不自动确认 ambiguous/cross-city/missing resolution；不直接创建 revision。 |
| URL | `imports/url` → URL policy/DNS/robots → bounded fetch → raw artifact + derived text → review | 可审查 derived plain text、fetch provenance、mentions 与显式 review。 | robots、TLS、DNS、redirect、login wall、dynamic page、内容类型或大小限制失败须返回稳定错误；建议用户粘贴文字。策略在 artifact/job 前拒绝时，不伪称已保存 source。 | 不绕过 robots、登录墙、SSRF/DNS rebinding 或 TLS；不转发 cookie/auth；不渲染 raw HTML 或执行页面 JavaScript。 |
| Image | `imports/artifacts` → quarantine → inspection → sanitized derivative → explicit document extraction → review | 检查通过的 `artifact_ready`、metadata-stripped sanitized preview；OCR 产生可追溯 derived text 后才可 review。 | 不支持、类型不符、损坏或危险文件保持 rejected/quarantined 语义；OCR 不可用或提取不足时保持 explicit partial/failed，而非 ready。 | 不信任浏览器 MIME/文件名；不服务原始 binary；不在 inspection 前 OCR/提取 mention；不直接创建 candidate/revision。 |
| PDF | `imports/artifacts` → quarantine → inspection → `artifact_ready` → native-text-first / selective OCR extraction → review | page-level extraction evidence、derived text、generation/retry lineage 与显式 review。 | encrypted PDF 为 `needs_password`；active content、嵌入文件、页数等拒绝保持明确 finding/status；页级失败保留 partial/failed/retryable evidence。 | 不执行 JavaScript、附件或外部资源；不 inline original PDF；不将任一页成功夸大为全文 ready；不直接修改 itinerary。 |

`review_ready` 代表可供用户审查，`partial` 代表部分证据仍可见但不能被展示为完成，
`artifact_ready` 只代表二进制可进入受控提取，不代表 OCR 已可用、事实已验证或行程可执行。

## 共同的 release 禁止项

- `SourceArtifact`、`ImportJob`、`TripCandidate` 不得被另一条导入链复制或替换。
- canonical place identity、review version、idempotency 与 commit result 仍由确定性层所有。
- 失败、stale decision 或重复 commit 不得产生重复 candidate 或修改既有 itinerary。
- capability/runtime 信息不能提升 source、route 或 operating fact 的真实性等级。
- raw source、原始 image/PDF、storage path、cookie、authorization、API key 与内部网络信息不得出现在 UI、公开 API、fixture 输出或日志中。

## Batch 04 API / evaluation release gate

Batch 04 将既有 API fixture 收敛为一个 CI 可执行的 release gate。fixture 定义位于
`backend/tools/run_import_evaluation.py`，全都由本地 deterministic factories、stub
transport 或受控 extraction stub 生成；不读取外网、真实用户文件、cookie 或 secret。
机器可检查的索引位于 `backend/tests/fixtures/import_release_manifest.json`，由
`backend/tests/test_import_release_contract.py` 和 `backend/tests/test_import_release_gate.py`
校验其与 evaluator、focused tests 和 gate case 保持同步。

| 表单 | 正常闭环 gate | 降级/拒绝 gate | 共同不变量 |
| --- | --- | --- | --- |
| Text | `commit_confirmed_only` | `stale_review_conflict` | explicit review、stale rejection、idempotent commit、candidate-only mutation。 |
| URL | `url_commit_boundary` | `url_loopback_ipv4` | local fixture fetch、private destination rejection、candidate provenance、no TripRevision。 |
| Image | `image_ocr_review_to_candidate`（受控 OCR result） | `document_image_ocr_unavailable_explicit` | quarantine-first、OCR unavailable 不伪装成功、stale rejection、idempotent candidate commit。 |
| PDF | `document_pdf_native_text_to_review` | `document_pdf_partial_page_retry` | native-text-first、page retry lineage、partial 明确、candidate-only commit。 |

每一个 gate failure 都报告 `form`、`stage` 和稳定的 `reason_code`；输出不包含源文本、
文件字节、cookie、storage key、主机细节或 secret。当前 gate 使用 68 个 local fixtures、
121 项不变量（其中 35 项 `DOCUMENT_`）及 8 个 case；此记录只说明 API/evaluation
验证，浏览器实际 capability 的结果单列于下方。

2026-09-02 在干净临时 SQLite / memory artifact 环境重跑的结果为：68/68 fixtures、
8/8 release-gate cases；运行使用 121 项定义不变量，`failure_count=0`。

## 浏览器 Release Gate

`frontend/playwright.import-release.config.ts` 复用现有 `tests.e2e_fixture_app`
与临时 SQLite/artifact 根目录；没有真实网络、用户文件、cookie、密钥或外部 provider。
该 gate 设计用于在浏览器中验证 Text 与 fixture URL 的创建 → private artifact → review decision →
candidate commit、derived URL text 不渲染 raw HTML、private headers，以及 import commit
不创建 `TripRevision`。

2026-09-03 在当前 Codex 沙箱中，`npm run test:e2e:import-release` 的 Next build
通过，但 Playwright fixture backend 绑定 `127.0.0.1:8030` 时被运行环境拒绝（`[Errno 1]
operation not permitted`），升级权限重跑又被中断。因此本记录**不**宣称浏览器 gate
已经通过；不宣称 Text/URL 浏览器闭环已验证；也不宣称 image/PDF 上传、OCR 或 PDF
extraction 在该 runtime 跑通。API/evaluation gate 仍覆盖其受控正常与降级路径。完整限制
和可重跑条件见 release record。

## 发布 Runbook

### 前提

- backend 的 `.venv` 已安装测试依赖；frontend 已安装 `node_modules` 和 Playwright Chromium。
- 仅使用本地 fixture：不设置真实 API key，不把真实导入文件、cookie 或 private source 放入 fixture。
- browser gate 需要空闲的 `127.0.0.1:8030`/`:3030`；配置会自行创建临时 SQLite 和
  artifact 目录，并使用 `IMPORT_URL_FETCHER_MODE=fixture`。

### 验证顺序

从仓库根目录运行：

```bash
cd backend
./.venv/bin/python -m unittest \
  tests.test_import_release_contract \
  tests.test_import_release_gate \
  tests.test_text_import_foundation \
  tests.test_url_import_security \
  tests.test_binary_artifact_import
./.venv/bin/python -m tools.run_import_evaluation --ci

cd ../frontend
npm run test:workspace
npm run test:e2e:import-release
```

`test:e2e:import-release` 在 build 时固定 API proxy 到 `127.0.0.1:8030`；不要仅运行
裸 `playwright test` 后声称该 release gate 已验证。

### 失败排查与回滚/禁用

- 若 browser gate 无法启动，先检查上述两个本地端口和 Playwright Chromium；重跑前不要
  复用旧的 SQLite/artifact 目录或 capability snapshot。
- 若 snapshot 报 `binary_inspection_unavailable`、`ocr_unavailable` 或
  `pdf_renderer_unavailable`，保留该状态和 reason code；不得启用 binary submit，改用
  Text/URL 或在满足服务端前提的 fixture 环境重跑。
- 若 URL fixture 失败，确认 `IMPORT_URL_ENABLED=true` 和
  `IMPORT_URL_FETCHER_MODE=fixture`；不得改为 live network 以求通过。
- 若需停止某 form，服务端设置相应 capability 为 unavailable，并验证 UI 禁用该 form。
  这不删除既有 artifact、job、candidate 或 revision；恢复前需重跑完整 gate。

## 验证命令

从仓库根目录运行：

```bash
cd backend
./.venv/bin/python -m unittest \
  tests.test_import_release_contract \
  tests.test_import_release_gate \
  tests.test_text_import_foundation \
  tests.test_url_import_security \
  tests.test_binary_artifact_import
./.venv/bin/python -m tools.run_import_evaluation --ci
```

`python -m tools.run_import_evaluation --ci` 是当前 CI 可调用的 API/evaluation release gate。
该命令包含 8 个 API/evaluation release-gate cases；browser gate 使用上方的独立命令。

## 关联决策与阶段

- [ADR-0007：Text Import Provenance and Review Boundary](../decisions/0007-text-import-provenance-and-review-boundary.md)
- [ADR-0008：Secure URL Import and Fetch Provenance](../decisions/0008-secure-url-import-and-fetch-provenance.md)
- [ADR-0009：Quarantine-First Binary Artifact Inspection](../decisions/0009-quarantine-first-binary-artifact-inspection.md)
- [ADR-0010：Layout-Aware Document Text Extraction](../decisions/0010-layout-aware-document-text-extraction.md)
- [ADR-0011：Persist page-level document extraction evidence](../decisions/0011-page-level-document-extraction-evidence.md)
- [Current Product Phase](CURRENT_PHASE.md)

## 后续 Batch 的固定边界

- Batch 01 已实现服务端权威的 capability snapshot 与只读 endpoint；Batch 02 只能消费它，
  不能复制 capability 检测或将 runtime availability 当作导入成功。
- Batch 02 只消费该 snapshot，并复用既有 unified Import Review intake。
- Batch 03 只修复由 release matrix 暴露的真实 Review → Candidate 断点。
- Batch 04 已扩展现有 evaluation/API fixture 资产为可执行 release gate，未修改生产导入链路。
- Batch 05 已落地浏览器 release gate、runbook 与 release record。当前 Codex 沙箱未能完成
  browser gate 重跑；后续必须按 release record 重跑并只记录真实 fixture capability。

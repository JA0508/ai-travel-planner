# Import 全形式 Release 合同

## 状态与范围

本文是 Import 全形式 Release 的 Batch 00 基线合同，并记录截至 2026-08-30
已完成的 Batch 01 capability endpoint。它不是发布通过记录，也不声明四形式
release gate；该 gate 仍是后续 Batch 04 的工作。

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

## 当前验证资产：测试与 fixture 清单

下列是 Batch 00 锁定的真实基线，不是新增的 release gate。fixture 定义位于
`backend/tools/run_import_evaluation.py`，全都由本地 deterministic factories 或
stub transport 生成；不读取外网、真实用户文件、cookie 或 secret。
机器可检查的索引位于
`backend/tests/fixtures/import_release_manifest.json`，由
`backend/tests/test_import_release_contract.py` 校验其与 evaluator、文档和 focused
tests 保持同步。

| 表单 | focused tests | evaluator fixture 组 | 当前数量 | 基线覆盖 |
| --- | --- | --- | ---: | --- |
| Text | `backend/tests/test_text_import_foundation.py` | `FIXTURES` | 19 | spans、review version、candidate-only commit、idempotency、source-as-data。 |
| URL | `backend/tests/test_url_import_security.py` | `URL_FIXTURES` | 23 | redirect/robots/TLS/DNS/SSRF、derived text、login/dynamic/size 拒绝。 |
| Image/PDF intake | `backend/tests/test_binary_artifact_import.py` | `BINARY_FIXTURES` | 20 | quarantine、content detection、sanitization、PDF findings、private binary boundary。 |
| Document extraction | `backend/tests/test_binary_artifact_import.py` | `DOCUMENT_EXTRACTION_FIXTURES` | 5 | native text、OCR unavailable、page retry、reading order、page evidence。 |

在本基线环境中，既有 evaluator 报告 67 fixtures、121 total invariants，
其中 35 项以 `DOCUMENT_` 开头。这些数字是当前资产盘点；Batch 04 才负责把
release 所需的“四形式正常闭环 + 明确降级/安全拒绝”收敛为独立的 CI gate，
不得在此之前将数字当作 release approval。

## 验证命令

从仓库根目录运行：

```bash
cd backend
./.venv/bin/python -m unittest \
  tests.test_import_release_contract \
  tests.test_text_import_foundation \
  tests.test_url_import_security \
  tests.test_binary_artifact_import
./.venv/bin/python -m tools.run_import_evaluation --ci
```

CI 已执行 `python -m tools.run_import_evaluation --ci`，但 Batch 00 不修改
workflow，也不新增空壳 workflow。后续 Batch 必须在此基础上记录新增命令与
实际覆盖，不能仅引用本文便宣称发布已验证。

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
- Batch 04 只扩展现有 evaluation/API fixture 资产为可执行 release gate。
- Batch 05 才进行浏览器 release gate、runbook 与 release record；在实际验证前不得更新 `CURRENT_PHASE.md` 宣称该 release 完成。

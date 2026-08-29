# Import Capability Pack 合同（Batch 00）

## 状态

本文固定 Batch 01 要实现的服务端权威 capability snapshot 边界。它是设计合同，
不是已部署 API：Batch 00 没有新增 schema、endpoint、环境探测或前端读取逻辑。
在 Batch 01 的 contract tests 通过前，客户端不得假定 capability pack 可读取。

Capability pack 只回答“在当前安全运行条件下某种输入是否可尝试处理，以及为何降级”；
它不回答 source 是否真实、提取是否正确、地点是否 canonical、用户是否已授权 commit，
更不代表 itinerary 可执行。

## 所有权与访问控制

- 服务端组装 snapshot，并以现有 trip capability 保护读取；它不是用户权限系统，
  也不替代/返回 trip capability cookie。
- snapshot 是只读 runtime availability，不能成为上传、提取、review 或 commit 的授权。
- 每个实际操作仍必须经过既有输入验证、URL/binary 安全边界、review version、
  idempotency 与确定性服务。
- snapshot 可随运行时依赖改变；客户端只能把它作为当前加载结果，不能写入
  localStorage、不能缓存原始文件内容，也不能把它持久化为 trip domain fact。

## 最小公开模型（Batch 01 实现目标）

后续只读 response 的最小顶层字段如下。字段名在 Batch 01 schema test 中固定；
任何扩展都必须保留其隐私语义。

| 字段 | 类型/语义 | 公开约束 |
| --- | --- | --- |
| `schema_version` | 固定 capability response schema 版本。 | 不能用内部 package/host 信息代替版本。 |
| `forms` | text、url、image、pdf 四种 form 的完整列表。 | 不得因不可用而省略 form。 |
| `forms[].form` | 稳定枚举：`text`、`url`、`image`、`pdf`。 | 不接受任意客户端 form。 |
| `forms[].availability` | `available`、`degraded` 或 `unavailable`。 | 仅表达当前可执行条件，不表达事实确定性。 |
| `forms[].reason_codes` | 空或稳定、可本地化的机器 reason codes。 | 不返回异常堆栈、命令输出或环境原文。 |
| `forms[].processing_stages` | 对用户可见的安全阶段标识，例如 `source_artifact`、`inspection`、`document_extraction`、`review`。 | 不是内部队列/路径/worker 拓扑。 |
| `forms[].safety_boundary_codes` | 仍适用的安全边界标识。 | 说明保护，不暴露绕过方法或网络细节。 |

Batch 01 可以在不泄漏运行时细节的前提下，为安全 UI 禁用态增加经过审查的
display metadata；不得将“当前可用”混同为“上传已经检查通过”或“提取已完成”。

## 形式级语义

| form | `available` 的最低含义 | `degraded` 的最低含义 | `unavailable` 的最低含义 |
| --- | --- | --- | --- |
| text | 可使用既有文本创建与 review 链。 | 仅当文本自身的运行条件有已知、可解释限制。 | 不可安全创建文本 import；前端禁用提交。 |
| url | 可进入既有 URL policy/robots/bounded-fetch 链。 | 不得因二进制 OCR/rendering 缺失而降级。 | 不可安全发起 URL import；前端展示 reason 与粘贴文字替代建议。 |
| image | 可安全上传、inspection，且所需 document extraction/OCR 前提满足。 | upload/inspection 可用但 OCR 或后续提取前提不完整；不得标为 ready。 | 不能安全接收或处理 image；前端禁用提交。 |
| pdf | 可安全上传、inspection，且 native text/rendering/OCR 所需前提满足。 | 上传/inspection 可用但某些 extraction 前提缺失；加密或拒绝的单个文件仍由现有 job/finding 表达。 | 不能安全接收或处理 PDF；前端禁用提交。 |

每种 form 的实际 job 结果仍可能是 `partial`、`failed`、`rejected` 或
`needs_password`。这些 job 状态不会被 capability snapshot 覆盖，也不能由
客户端推断为成功。

## 严禁公开的字段

capability snapshot、reason code、日志、测试 fixture 输出与 UI 均不得包含：

- API key、token、cookie、authorization header、session/capability 原文；
- 原始 source 内容、上传字节、完整 URL 中的敏感 query 参数、artifact storage key 或绝对路径；
- 完整环境变量、命令行、堆栈、package install path、worker PID、internal DNS/IP、端口、host 或 provider credential；
- 用户、trip、artifact、import job、review decision 或 candidate 的可识别私有内容；
- 可用于绕过 URL robots/SSRF/TLS 或 binary quarantine 的内部策略细节。

安全的 reason code 应表达产品可行动原因（例如“document extraction temporarily
unavailable”），而非诊断主机配置原因。稳定 error/reason code 必须由服务端
枚举生成，不能透传异常文本。

## API 与兼容性边界

Batch 00 不分配 capability endpoint 路径，避免在实现前制造伪稳定 public API。
Batch 01 必须在本文件中补充已实现的只读 endpoint、response schema 版本、
trip capability 未授权语义和 contract-test 引用。它必须与既有下列 endpoint
并存，而不得改变它们的含义：

- `POST /trips/{trip_id}/imports/text`
- `POST /trips/{trip_id}/imports/url`
- `POST /trips/{trip_id}/imports/artifacts`
- `POST /trips/{trip_id}/imports/{import_job_id}/extract-document`
- `POST /trips/{trip_id}/imports/{import_job_id}/commit`

客户端在 snapshot 缺失、读取失败或版本不兼容时，必须显示未知/无法确认 runtime
availability 的状态；不能臆测四种 form 都可用，也不能把未知显示为 `available`。

## Batch 01 验收测试清单

- 四种 form 始终出现，并在正常、降级和不可用运行条件下返回稳定 availability/reason codes。
- OCR/rendering 缺失时 image/PDF 不得为 ready；text/URL 不得被无关二进制能力影响。
- 未携带有效 trip capability 的请求被拒绝，且 response 不泄漏 snapshot 内容。
- response 与 error body 不含本文件“严禁公开”的值；测试应使用 canary secret/path/host 验证 redaction。
- 读取 snapshot 不创建 artifact/import job/review decision/candidate/revision，也不触发 fetch、upload 或 extraction。

## 关联资料

- [Import 全形式 Release 合同](../product/IMPORT_FULL_FORMAT_RELEASE.md)
- [ADR-0007](../decisions/0007-text-import-provenance-and-review-boundary.md)、[ADR-0008](../decisions/0008-secure-url-import-and-fetch-provenance.md)、[ADR-0009](../decisions/0009-quarantine-first-binary-artifact-inspection.md)、[ADR-0010](../decisions/0010-layout-aware-document-text-extraction.md)、[ADR-0011](../decisions/0011-page-level-document-extraction-evidence.md)
- [Current Product Phase](../product/CURRENT_PHASE.md)

# Import 全形式 Release 闭环与能力包管理：Batch Checklist

- [x] Batch 00 — Release Contract、能力矩阵与基线（文档/测试边界）
- [x] Batch 01 — 服务端 Import Capability Pack 合同
- [x] Batch 02 — 前端 Capability-Aware Unified Import Intake
- [x] Batch 03 — 全形式 Review → Candidate 闭环一致性
- [x] Batch 04 — 四形式 API 与评测 Release Gate
- [x] Batch 05 — 浏览器 Release Gate、Runbook 与发布记录（当前环境未取得 browser pass）

## 调度记录

| Batch | 对话 | 状态 | Commit | 启动/完成时间 | 备注 |
|---|---|---|---|---|---|
| 00 | 01a0330d-a0ed-7362-a6e4-1970602a401d | completed | 本地 Batch 00 提交 | 2026-08-30 | 文档、fixture manifest 与 focused test；未改生产 API、业务逻辑或 UI |
| 01 | 01a05029-e292-7e32-bd3c-84900bcff739 | completed | 本地 Batch 01 提交 | 2026-08-30 | 服务端 capability pack、Trip capability 只读 endpoint、contract/redaction tests；未改 upload、fetch、extraction、review 或前端 |
| 02 | 01a05310-3160-7fb1-825d-5d02b22acc3f | completed | 本地 Batch 02 提交 | 2026-08-31 | 前端 capability-aware intake、四形式禁用/降级语义与 focused tests；未改后端、review 闭环或二进制流程 |
| 03 | 01a05a62-45b3-7852-be4e-a19919ff498f | completed | 本地 Batch 03 提交 | 2026-09-01 | 补齐 image 经检查、OCR 派生、review、candidate commit/replay 的回归闭环；未改生产导入架构或发布门禁 |
| 04 | 01a0330d-a0ed-7362-a6e4-1970602a401d | completed | 本地 Batch 04 提交 | 2026-09-02 | 本地 API/evaluation release gate：四形式正常闭环、URL 安全拒绝、image OCR unavailable、PDF partial/retry、stale 与 idempotency；68 fixtures / 8 gate cases，未改生产导入链路、浏览器或最终发布记录。 |
| 05 | 当前对话 | completed with environment limitation | 本地 Batch 05 提交 | 2026-09-03 | 新增 fixture-only browser release gate 与 runbook/release record。当前 Codex 沙箱中 `next build` 通过，但 fixture backend 绑定 `127.0.0.1:8030` 被拒绝，升级权限重跑被中断；未声称 browser gate 或外部发布通过。 |

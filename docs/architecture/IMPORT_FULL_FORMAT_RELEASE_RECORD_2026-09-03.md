# Import 全形式 Release Record — 2026-09-03

## Disposition

本记录收口 Import 全形式 Release 的 Batch 05 gate、runbook 与 release-record 工作。
结论是：浏览器 gate 已作为可重跑命令落地，但当前 Codex 沙箱未完成通过验证；**不是**
生产部署、外部发布、browser gate passed，或所有运行环境均具备 OCR/binary processing
的声明。

所有已验证的 API/evaluation evidence 使用本地 fixture、临时 SQLite 和临时 artifact
根目录；没有外网、真实用户文件、cookie、provider credential 或 private source。

## Evidence

| Surface | Actual result | What it proves |
| --- | --- | --- |
| API/evaluation gate | 68/68 local fixtures、8/8 gate cases、121 invariants passed | Text、URL、image、PDF 的受控正常/降级/拒绝语义，含 stale、idempotency 与 candidate-only mutation。 |
| Browser gate implementation | `frontend/playwright.import-release.config.ts` and `frontend/tests/e2e-import-release/import-release.spec.ts` added | Provides a fixture-only browser gate that should exercise Text/URL review-to-candidate closure and fail-closed binary capability rendering when the environment can bind local servers. |
| Browser gate load check | `npx playwright test --config=playwright.import-release.config.ts --list` listed 1 test | The new Playwright config/spec can be discovered without starting servers; this is not browser-flow evidence. |
| Browser gate execution in this Codex session | `npm run test:e2e:import-release` completed `next build`, then failed before Playwright assertions because fixture backend binding `127.0.0.1:8030` returned `[Errno 1] operation not permitted`; an escalated rerun was interrupted | Current session does not provide browser-pass evidence. No Text/URL browser closure, Image/PDF upload, OCR, or PDF extraction result is claimed from this run. |

Browser command:

```bash
cd frontend
npm run test:e2e:import-release
```

API/evaluation commands are retained in
[Import Full-Format Release](../product/IMPORT_FULL_FORMAT_RELEASE.md).

## Matrix interpretation

| Form | Browser observation on 2026-09-03 | Release statement |
| --- | --- | --- |
| Text | Not observed to pass in this session because Playwright stopped before assertions. | Browser closure remains pending rerun. |
| URL | Not observed to pass in this session because Playwright stopped before assertions. | Browser closure remains pending rerun; no live-website claim. |
| Image | Not observed to pass in this session because Playwright stopped before assertions. | Browser fail-closed/upload/OCR behavior remains pending rerun in an environment with local server binding. |
| PDF | Not observed to pass in this session because Playwright stopped before assertions. | Browser fail-closed/upload/native-text/page-preview behavior remains pending rerun in an environment with local server binding. |

## Known limitations and rerun conditions

The current Codex sandbox did not allow the fixture backend to bind the configured local port,
so the browser gate could not reach runtime capability observation. This is an execution
environment limitation, not a product success and not enough evidence to approve release.
Do not claim image/PDF browser extraction, Text/URL browser closure, or fail-closed rendering
passed from the API gate alone.

To obtain binary browser evidence, provision a fixture environment where the server capability
snapshot reports Image/PDF as `available` or `degraded` rather than unavailable, then run the
same browser gate with local audit-safe image/PDF fixtures. Confirm separately that sanitized
image and document-page preview responses remain `private, no-store` and `nosniff`, that raw
binary never renders inline, and that commits still leave `TripRevision` unchanged.

To reproduce the current Batch 05 browser gate, allow local binding on `127.0.0.1:8030` and
`127.0.0.1:3030`, then run:

```bash
cd frontend
npm run test:e2e:import-release
```

Record the exact pass/fail output before changing this release statement to passed.

If binary capability needs to be disabled in an operational environment, keep the server-side
capability snapshot unavailable and rerun the browser gate. Existing artifacts, review jobs,
candidates and revisions must remain untouched; disabling intake is not deletion or migration.

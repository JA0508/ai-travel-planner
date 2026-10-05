# Public beta preparation — 2026-10-05

Status: preparation branch only, **not approved for public release**.

## Delivered

- Next.js 15.5.27, React/React DOM 19.0.8 and Playwright 1.63.0.
- Explicit PostCSS 8.5.28 / nanoid 3.3.19 overrides resolve vulnerable transitive
  dependencies still selected by Next 15. Reassess overrides on future upgrades.
- Production startup rejects wildcard/non-HTTPS origins and insecure trip cookies
  before calling providers. `/health` is a minimal local liveness endpoint;
  `/readiness` remains the provider/persistence diagnostic endpoint.
- Controlled same-origin Docker Compose/Caddy recipe, required edge credentials,
  server-only secret files, persistent SQLite/import storage and offline backup
  tooling. See [deployment runbook](controlled-preview-deployment.md).
- Updated browser assertions to follow the existing changing primary-action label
  and the selected day panel. Failure-injection tests exclude their deliberately
  injected response only; unexpected API failures remain failures.

## Verification

- `npm audit` and `npm audit --omit=dev`: zero known vulnerabilities.
- `npm run typecheck`: passed.
- `npm run test:workspace`: 180 passed; `npm run test:browser-smoke`: 82 passed.
- `npm run test:e2e:intent`: initial run found stale selectors/day selection;
  final `npx playwright test --config=playwright.intent.config.ts`: 17 passed
  against the same successful production build.
- `npm run test:e2e:trip-compiler`: production build passed, 51/54 tests passed.
  The injected 409/503 test incorrectly failed its own network gate; after the
  scoped fix its targeted rerun passed (1/1). The full suite is **not green**:
  two version-history restore tests still require the missing version-history
  entry point on `/trip-compiler`. They were not removed or skipped.
- `AMAP_API_KEY= OPENAI_API_KEY= .venv/bin/pytest -q`: 477 passed, 3 skipped.
  This includes production guards and liveness; fixtures use no real API keys.
- `python3 -m unittest discover -s infra -p 'test_backup.py'`: 2 passed.
- Compose `config --quiet` passed with disposable placeholder configuration.
- Gitleaks scanned all 114 previously unpushed commits and infra: no leaks found.
- `git diff --check`: passed.

## Remaining release gates

1. Implement product invitation acceptance, account sessions/revocation and
   account-to-trip ownership, with two-account cross-access denial tests for trips,
   revisions, imports and planning runs. Existing bearer capabilities are not an
   account system; edge Basic Auth is not a substitute.
2. Wire supported revision history into the compiler route surface and pass both
   outstanding restore E2E tests, then rerun the complete release suites.
3. Build and run containers on a Docker-enabled host. Docker daemon was unavailable
   locally, so image build, Caddy runtime and TLS behavior remain unverified.
4. Supply an actual domain/host and privately provision credentials. Verify DNS,
   HTTPS redirect, anonymous denial at both page/API, closed backend ports,
   production provider behavior, monitoring and a restore drill.
5. Configure scheduled encrypted off-host backups and retention. The provided
   script is a manual consistent snapshot foundation, not an operated backup service.

No public deployment, DNS change, invitation or credential provisioning occurred.
CI has not been established green for this preparation branch.

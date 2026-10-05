# Controlled preview deployment

This recipe is for one operator and trusted testers only. It is **not public release
approval**: HTTP Basic authentication at the edge is a temporary admission gate,
not product accounts, invitations, or per-user ownership. Existing trip capability
cookies do not establish full user isolation. Keep this gate enabled until product
authentication, ownership checks for all trip/import routes, rate limiting, and
multi-user privacy tests are delivered and reviewed. Do not host unrelated users'
private travel documents in this shared preview.

## Topology and secrets

Docker Compose v2 runs Caddy → Next.js → FastAPI on one server. Only Caddy publishes
ports. Caddy obtains/renews HTTPS certificates; frontend rewrites `/api` to the
internal backend address at build time. The browser uses same-origin `/api`.
Backend secrets never enter frontend build arguments or `NEXT_PUBLIC_*` values.

1. Point a hostname's DNS A/AAAA records at the server, allowing inbound 80/443.
   Remove an AAAA record unless the server actually supports IPv6. Do not expose
   3000/8000. Choose the server region and any registration requirements before use.
2. Copy `infra/.env.example` to a private server path such as
   `/srv/trip-secrets/deploy.env`; set the real hostname (no scheme/path), absolute
   `ACCESS_FILE`, and `BACKEND_ENV_FILE` paths. Keep the directory owner-only.
3. Copy `backend/.env.example` outside the repository to that backend env path.
   Configure provider credentials there. Production requires the AMap key;
   configure an LLM key only if that capability is desired. The Compose environment
   overrides persistence, CORS, cookie security and production mode. Both allowed
   origin lists contain only `https://<PUBLIC_DOMAIN>`.
4. Generate a hash interactively with
   `docker run --rm -it caddy:2.10-alpine caddy hash-password`.
   Copy `infra/access.caddy.example` to `ACCESS_FILE` and replace its invalid hash.
   Keep this file outside Git with mode 600. Caddy's auth file is a required mount;
   missing credentials prevent a usable site. Use unique tester passwords where
   practical; revocation requires removing the entry and reloading Caddy.
5. From repository root, use the command below. Do not print expanded Compose
   configuration into logs: it includes backend environment values.

```bash
docker compose --env-file /srv/trip-secrets/deploy.env -f infra/compose.yaml config --quiet
docker compose --env-file /srv/trip-secrets/deploy.env -f infra/compose.yaml up -d --build
```

`trip-data` stores SQLite, immutable imports and transient staging. Caddy certificate
state has separate persistent volumes. Never run `down --volumes` on this deployment.
The backend deliberately uses one worker. Scale-out with shared SQLite is unsupported.
Images use maintained version tags but not digest locks; record resolved image IDs
and the Git commit for each deployment and pin tested digests in the release process.

Dockerfile-specific ignore files exclude local `.env`, data, dependencies and build
output. Images run as non-root app users. OCR packages for English/Chinese are
included; the browser map SDK is not configured by this recipe. No access logs are
enabled at the edge/backend to avoid storing private URLs. Add redacted operational
monitoring separately before wider rollout.

## Verification before inviting a tester

- Anonymous HTTPS access to both `/` and `/api/health` returns 401; HTTP redirects
  to HTTPS. Check this externally, including direct server ports (3000/8000 closed).
- With a tester credential, load the homepage and `/api/health`, submit a fixture
  request, confirm locations, obtain a preview and reload its durable state.
- Confirm trip capability cookies have Secure, HttpOnly and the intended SameSite
  behavior in browser developer tools; foreign Origin mutation requests fail.
- Restart the backend and confirm the saved trip and import still load.
- Confirm no secrets appear in browser bundles/network responses or logs.
- Execute the backup/restore drill below against disposable volumes. This repository
  change alone does not establish successful DNS/TLS/container/provider validation.

## Backup and restore drill

Back up database and artifact files together while **all writers are stopped**.
SQLite's online backup API includes WAL commits, but copying artifacts concurrently
would not produce a consistent pair. Plan a short maintenance window. Do not restart
the backend until backup completes. Create a new unique snapshot directory per run.
Provision `/srv/trip-backups` owned by UID 10001 with mode 700 beforehand.

```bash
docker compose --env-file /srv/trip-secrets/deploy.env -f infra/compose.yaml stop backend
docker compose --env-file /srv/trip-secrets/deploy.env -f infra/compose.yaml run --rm --no-deps -v /srv/trip-backups:/backups backend python /opt/backup.py --writers-stopped --target /backups/snapshot-YYYYMMDD-HHMMSS
docker compose --env-file /srv/trip-secrets/deploy.env -f infra/compose.yaml start backend
```

Only snapshots containing `complete.json` are complete. A failed run can leave a
partial directory; retain for investigation, never restore it. Backups contain
private data: encrypt and copy off-host using your backup service, restrict access,
retain according to your policy, and test recovery regularly. The script does not
configure encryption, scheduling, retention or off-host storage.

To restore: stop all services; preserve the current volume as rollback evidence;
create a **new empty** volume; verify `complete.json`, run SQLite `PRAGMA integrity_check`
on its database, and copy `trips.sqlite3` and `import-artifacts/` into that new volume.
Set ownership to UID/GID 10001. Do not copy old `-wal`/`-shm` files or staging files.
Point a reviewed Compose override at the new volume, start the same application
commit used for backup, and validate a known trip and artifact before admitting
traffic. Keep the old volume until recovery is accepted. Never overwrite a live
database. Schema rollback across different app versions is not guaranteed.

Automated local check: `python3 -m unittest discover -s infra -p 'test_backup.py'`.

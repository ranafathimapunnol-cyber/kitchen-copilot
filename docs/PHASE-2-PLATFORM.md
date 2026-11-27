# Phase 2 — Organisation platform (SUPER_ADMIN)

Built 27 November 2026. **Migration M1 (`d5e8f0b2a314`) applied to the
development database on 27 Nov 2026 19:46 after explicit authorization**
(section 9). No platform account exists yet. Nothing here is ACCEPTED or
DEPLOYED.

Hierarchy: **organisation → campuses → campus users → campus records.**

## 1. Authentication and permission design

| | Campus app (`/dashboard`) | Platform app (`/platform`) |
|---|---|---|
| Sign-in | `POST /api/auth/login` | `POST /api/platform/auth/login` |
| Accounts | ADMIN, KITCHEN_MANAGER, STAFF (campus required) | SUPER_ADMIN only (no campus) |
| Session | `access_token` + `refresh_token` cookies, SECRET_KEY | `platform_access_token` cookie, own derived key, `PLATFORM_SESSION_MINUTES` (30), no refresh |
| Sign-out | clears cookies | revokes every platform session of the account, then clears the cookie |
| Audit | `audit_logs` (campus) | `platform_audit_logs` (append-only) |

- A platform token never verifies as a campus token and the reverse (separate
  signing keys, separate cookie, `type` claim).
- `get_current_user` (every campus endpoint) refuses SUPER_ADMIN accounts and
  accounts without a campus; `require_permission`/`user_has_permission` deny
  SUPER_ADMIN every campus permission. A platform account therefore has **no
  campus operational access**, including no Copilot.
- `get_platform_user` (every platform endpoint) accepts only an active
  SUPER_ADMIN with no campus, a valid platform token, the current password
  fingerprint and no revocation. Campus accounts get 401 on every platform
  route.
- Platform sign-in: same throttle as the campus sign-in (5 failures per email,
  30 per address, 15 minutes); one generic failure message; every attempt
  (success, failure, throttled) is written to the platform audit with reason.
- The campus sign-in refuses a SUPER_ADMIN (pointing to the platform sign-in)
  and users of a deactivated campus.
- No registration anywhere. The first platform account is created by the
  operator: `python -m scripts.create_super_admin "Name" email [--organization-id N]`
  (emails a single-use setup link; needs SMTP and FRONTEND_BASE_URL; no
  default password). Platform accounts may use password setup/reset links;
  those events go to the platform audit.
- A SUPER_ADMIN with `organization_id` sees and manages only that
  organisation's campuses; one without sees all campuses (and alone may add
  organisations).

## 2. What the platform can see

Campus **aggregates only**, computed by the same functions as the campus
dashboard: user counts by role, purchase totals and bill counts for a period,
outstanding payables, items below minimum / out of stock, pending stock
adjustments, meal records still open from earlier days, draft meal plans, last
campus activity time. It never lists a campus's bills, stock lines, meals or
audit entries. Campus user lists are read-only (name, email, role, status,
last sign-in); each campus's Admin keeps managing its users and STAFF grants.

## 3. Backend

Files: `app/api/platform_auth.py`, `app/api/routes/platform.py`,
`app/services/platform_summary.py`, `app/services/erp_headcount.py`,
`app/models/platform.py`, `app/models/organization.py`, `scripts/create_super_admin.py`;
changed `app/models/user.py`, `app/models/campus.py`, `app/core/config.py`,
`app/core/security.py`, `app/api/dependencies.py`, `app/api/routes/auth.py`,
`app/services/password_management.py`, `app/main.py`; migration
`migrations/versions/d5e8f0b2a314_platform_super_admin.py`.

Endpoints (all `/api/platform`, all need M1 — 503 with a clear message before it):

| Method | Path | Purpose |
|---|---|---|
| POST | `/auth/login`, `/auth/logout`; GET `/auth/me` | platform session |
| GET | `/overview?date_from&date_to&campus_id` | totals, per-campus summary, alerts, recent platform activity |
| GET | `/analytics?date_from&date_to&campus_id` | purchases by campus and by month |
| GET/POST | `/organizations` | list / add (all-organisations administrators only) |
| GET/POST | `/campuses?status&q` | list / register (case-insensitive unique name and code) |
| GET/PATCH | `/campuses/{id}` | detail with operational summary / edit details (code fixed) |
| POST | `/campuses/{id}/deactivate` (reason), `/campuses/{id}/activate` | lifecycle; nothing deleted |
| GET | `/campuses/{id}/users`, `/users?scope&campus_id&role&q` | read-only accounts |
| POST | `/campuses/{id}/admins` | invite the campus Admin by setup link |
| GET | `/audit?action&outcome&campus_id&date_from&date_to&page` | platform audit viewer |
| GET | `/integrations`; PUT `/campuses/{id}/integrations/erp-headcount`; POST `.../sync` | ERP settings and status |
| GET | `/health` | API, database, jobs, Copilot, storage, email, ERP, campuses — no secrets |

Audited actions: LOGIN (success/failure/denied), LOGOUT, CREATE (campus,
organisation, platform user by the operator), UPDATE, DEACTIVATE, ACTIVATE,
PROVISION_ADMIN, CONFIGURE_INTEGRATION, ERP_SYNC, password setup/reset events
of platform accounts. Each row: actor, email, action, target, campus, outcome,
IP address, time, details.

**Works before M1.** The new campus/user columns are deferred and marked
server-generated, so campus code never selects them and INSERTs leave them out;
verified on an un-migrated copy (section 6). The platform answers 503 until M1.

## 4. Frontend

Separate app, its own navigation and session: `/platform/login`, `/platform`
(organisation overview), `/platform/campuses`, `/platform/campuses/[id]`,
`/platform/analytics`, `/platform/users`, `/platform/audit`,
`/platform/integrations`, `/platform/health`, `/platform/settings`.
Files: `src/app/platform/**`, `src/components/platform/*`, `src/lib/platform.ts`;
changed `src/lib/api/client.ts` (platform requests never use the campus
refresh; 401 → platform sign-in), `src/lib/auth/permissions.ts` (SUPER_ADMIN
reaches no `/dashboard` screen), `src/lib/navigation.ts` (platform entry
removed from campus navigation), `src/app/login/page.tsx` (link to the
platform sign-in), `src/app/dashboard/platform/page.tsx` (now redirects to
`/platform`). Bold Minimal Light/Dark tokens, lime only as a fixed accent chip.

## 5. ERP headcount adapter (Phase 3 preparation)

`app/services/erp_headcount.py`: per-campus base URL (HTTPS only), on/off,
timeout and retries in `campus_integrations`; the credential only from the
environment (`ERP_HEADCOUNT_API_TOKEN`), reported as set / not set; HTTP
transport with timeout, bounded retries with back-off on network errors,
429 and 5xx, and credential redaction; idempotency ledger
`erp_headcount_imports` (unique campus + ERP key, content hash: new /
unchanged / changed-since-applied / duplicate-in-batch); sync runs with status
and sanitised error. **No endpoint, auth scheme, field or response format is
implemented**: `fetch_headcounts`, `validate` and `apply_record` raise
"contract pending". Status shows **"ERP connection not configured"** until a
base URL and server credential exist, then "Waiting for the ERP API
documentation". Manual headcount entry is unchanged.

## 6. Migration review — `d5e8f0b2a314` (M1)

Revises `c4d7e9a1f203` (current dev head). Additive only:

1. `userrole` + `SUPER_ADMIN` (autocommit block); `users.campus_id` nullable +
   check `ck_user_campus_by_role` (only SUPER_ADMIN has no campus);
   `users.organization_id`.
2. `organizations`; `campuses.organization_id`, address, contact name / email
   / phone, created / updated / deactivated time, deactivation reason (all
   nullable); case-insensitive unique indexes on campus and organisation name
   and code (upgrade stops first if existing campuses differ only by case).
3. `platform_audit_logs` + triggers refusing UPDATE, DELETE, TRUNCATE.
4. `campus_integrations`, `erp_sync_runs`, `erp_headcount_imports`.

`audit_logs.campus_id` stays NOT NULL (platform events have their own table).
No existing row, permission or STAFF grant is touched.

**Authorization guard:** the upgrade refuses (before any change) unless
`KC_AUTHORIZE_M1=d5e8f0b2a314` is set. The API container runs
`alembic upgrade head` at start, so a rebuilt API image will **refuse to start**
on the development database until M1 is authorized — it cannot apply M1 by
accident. Do not rebuild the API image before authorization.

**Downgrade** removes only what M1 added and refuses while any SUPER_ADMIN,
organisation, platform audit row, integration setting or ERP record exists.
The enum value stays (PostgreSQL cannot drop one; harmless when unused).

Throwaway verification (27 Nov 2026), on a database restored from the verified
backup `~/kitchen-copilot-backups/pre-docker-stack-20261127-100821`
(not the live database), working-tree code:

| Check | Result |
|---|---|
| Restore | 52 tables at `c4d7e9a1f203` |
| Working-tree API before M1 (campus reads for Admin/KM/Staff, Admin creates a user, platform 503) | 16/16 |
| `alembic upgrade head` without authorization | refused; schema unchanged (no table, no enum value) |
| Upgrade with authorization | `c4d7e9a1f203 → d5e8f0b2a314` |
| Every existing table, row count and content hash (52 tables, 668 rows) | identical before and after |
| New tables, enum value, nullable campus_id, check, 4 CI indexes, audit triggers; existing ledger/plan triggers | all present |
| Downgrade with no platform data | back to `c4d7e9a1f203`; all 52 tables identical to the baseline; no new objects left |
| Upgrade again, add a platform account, downgrade | refused ("platform data exists"); version unchanged |
| Browser, platform + campus experiences + Phase 1 Copilot | 52/52 |

## 7. Interim decisions (not client decisions)

- Platform session 30 minutes, no refresh; sign-out revokes every platform
  session of the account.
- Deactivating a campus blocks its users' sign-in and existing sessions
  (403 with an explanation); accounts and records are untouched. No other
  effect (e.g. no notification) until the client decides.
- A campus code is fixed after registration (used on documents).
- Organisation-wide figures are aggregates; the platform never opens campus
  records. Organisation subscription/licence data does not exist in the
  current business model, so none is shown.
- ERP sync runs only on request (no scheduler) until the contract and timing
  are known.

## 8. Next safe step (only after explicit authorization of M1)

```sh
cd ~/Desktop/kitchen-copilot
# 1. Backup, then verify it lists cleanly
B=~/kitchen-copilot-backups/pre-d5e8f0b2a314-$(date +%Y%m%d-%H%M%S); mkdir -p "$B"
docker exec kitchen-copilot-db-1 pg_dump -U kitchen -d kitchen_copilot_db -Fc > "$B/docker_kitchen_copilot_db.dump"
docker exec -i kitchen-copilot-db-1 pg_restore --list < "$B/docker_kitchen_copilot_db.dump" | grep -c "TABLE DATA"
# 2. Apply exactly M1 with the working-tree code (one-off container)
docker compose run --rm --no-deps -T -e KC_AUTHORIZE_M1=d5e8f0b2a314 \
  -v "$PWD/services/api:/app/services/api:ro" api alembic upgrade d5e8f0b2a314
# 3. First platform account (needs SMTP and FRONTEND_BASE_URL in services/api/.env)
docker compose run --rm --no-deps -T -v "$PWD/services/api:/app/services/api:ro" \
  api python -m scripts.create_super_admin "Full Name" owner@your-domain
# 4. Rebuild and restart, keeping the local Gemini-off override
docker compose -f compose.yaml -f <local-safety-override> --profile core up -d --build api web
```

## 9. Applied to the development database (27 Nov 2026)

- Before: `kitchen_copilot_db` (Docker `kitchen-copilot-db-1`, port 5433) at `c4d7e9a1f203`.
- Backup: `~/kitchen-copilot-backups/pre-d5e8f0b2a314-20261127-194541/docker_kitchen_copilot_db.dump`
  (custom format, 54 table-data entries, SHA-256 495d72c0468dab16…); restored into a throwaway
  database: 52 tables, 711 rows, every table hash identical to the live database.
- Applied with `KC_AUTHORIZE_M1=d5e8f0b2a314 alembic upgrade d5e8f0b2a314` (one-off container,
  working-tree code): `c4d7e9a1f203 -> d5e8f0b2a314`.
- After: all 52 existing tables identical (711 rows, content hashes unchanged — campuses, users,
  purchases, stock movements, audit logs, STAFF grants, permissions); attachment files unchanged
  (0 files, 0 rows); new tables, SUPER_ADMIN enum value, check constraint, 4 CI indexes and
  platform audit triggers present; existing ledger/plan triggers intact; 0 SUPER_ADMIN, 0
  platform audit rows.
- Tests: full backend suite 817 passed; read-only smoke of the working-tree API on the migrated
  development database 37/37; running Docker stack (old images, not restarted) healthy.
- Not done (awaiting instruction): first platform account, image rebuild/restart.

## 10. Campus logo and photo (27 Nov 2026) — migration M2 `e2b7c4d9a5f1` NOT applied

- **Who:** platform administrators upload, replace and remove (campus page →
  "Logo and photo"); every signed-in user of a campus sees **their own
  campus's** logo in the campus app sidebar. Campus users cannot upload and
  cannot read another campus's images.
- **Safety:** only PNG, JPEG or WebP by content (not by name), at most 5 MB
  and 40 megapixels, at least 32 px. Every upload is re-encoded with Pillow:
  rotated upright, resized (logo PNG ≤ 512 px with transparency; photo JPEG
  ≤ 1600 px), all metadata removed (EXIF, GPS, camera). The original bytes are
  never stored. Files live in the private attachment storage under
  `campus-<id>/branding/<kind>-<random>.<ext>` and are served only through the
  API with `nosniff` and a restrictive CSP. Replacing or removing deletes the
  previous file.
- **Audit:** UPLOAD_MEDIA (success / failure with reason) and REMOVE_MEDIA in
  the platform audit log.
- **API:** `PUT|DELETE|GET /api/platform/campuses/{id}/media/{logo|photo}`;
  `GET /api/campus-media` and `/api/campus-media/{logo|photo}` (own campus).
- **Migration M2 (`e2b7c4d9a5f1`, revises `d5e8f0b2a314`):** adds
  `campuses.logo_key`, `photo_key`, `media_updated_at` (nullable). Same
  authorization guard (`KC_AUTHORIZE_MIGRATION=e2b7c4d9a5f1`). Throwaway check
  on a copy of the current development data: guard refuses without
  authorization; upgrade and downgrade leave all 57 tables / 758 rows
  identical; downgrade refuses while any campus has an image.
- **Before M2:** everything else works; the platform shows "available once
  migration e2b7c4d9a5f1 is applied" and campuses simply have no images.
- **Important:** the API container runs `alembic upgrade head` at start. Until
  M2 is authorized and applied, **do not rebuild the API image** (the new
  image would refuse to start). Restarting the current container is safe.
- **Tests:** `tests/test_campus_media.py` 13 passed; browser 19/19.

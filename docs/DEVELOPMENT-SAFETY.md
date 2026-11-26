# Development Safety Guide — Databases, Tests and Backups

This guide lists the commands that are safe to run during development and the
ones that must be avoided. Read it before running any database, migration or
test command.

## 1. Which database is which

| Name | Where | Host port | Used by | Status |
|---|---|---|---|---|
| `kitchen_copilot_db` | Docker container `db` | **5433** | The running application (`api` container) | **Authoritative** development database |
| `kitchen_copilot_test_db` | Docker container `db` | 5433 | Backend automated tests only | Created and emptied by the tests |
| `kitchen_copilot_db` | PostgreSQL installed on the host (Homebrew) | **5432** | Nothing at present | **Preserve. Do not modify, migrate or delete.** Its future is a separate decision. |

`services/api/.env` currently points at the **host** database on port 5432.
Inside Docker Compose, the `api` service overrides `DATABASE_URL` so that the
application uses the Docker database. As a result:

> Any Python, `pytest` or `alembic` command started from the host shell in
> `services/api` connects to the host (Homebrew) database, not to Docker.

## 2. Never run these from the host shell

| Command | Why it is unsafe |
|---|---|
| `pytest` (in `services/api`) | Connects to the host server and creates `kitchen_copilot_test_db` there on startup, even with `--collect-only` |
| `alembic upgrade …` / `alembic downgrade …` | Migrates the host database; the role migration cannot be reversed accurately |
| `python scripts/seed.py` | Writes demo data to the host database |
| `pytest spikes/ai/test_spikes.py` against a database that holds real data | `test_pgvector_retrieval_respects_campus` creates the `ai_spike` schema and writes rows into whichever database `DATABASE_URL` names. CI runs it against its own temporary database, which is safe. Locally, use section 3.4 |
| `DROP DATABASE`, `TRUNCATE`, `docker compose down -v` | Destroys data. `-v` deletes the Docker database volume |

## 3. Safe commands

All commands below are run from the project root.

### 3.1 Check the status of the Docker database

```bash
# Current migration revision of the application database
docker compose exec -T db psql -U kitchen -d kitchen_copilot_db -At \
  -c "select version_num from alembic_version;"

# Which database the running API uses (prints host and database name only)
docker compose exec -T api python -c "import os,re; m=re.match(r'[^:]+://[^@]*@([^:/]+):?\d*/(\S+)', os.environ['DATABASE_URL']); print(m.group(1), m.group(2))"
```

Expected: revision `d4e8a91b2c70`; API target `db kitchen_copilot_db`.

### 3.2 Check the migration graph (no database needed)

```bash
docker compose exec -T api alembic heads
```

There must be exactly one line ending in `(head)`.

### 3.3 Run the backend tests

The tests use `kitchen_copilot_test_db` on the **Docker** server. Each test
creates its tables and drops them afterwards. They never open
`kitchen_copilot_db`.

Tests exactly as built into the running image:

```bash
docker compose exec -T -e PYTHONDONTWRITEBYTECODE=1 api \
  python -m pytest -p no:cacheprovider tests -q
```

Tests from the current working tree (for example new, uncommitted tests), in a
temporary container from the same image, with the source mounted read-only:

```bash
docker compose run --rm --no-deps -T -e PYTHONDONTWRITEBYTECODE=1 \
  -v "$PWD/services/api:/app/services/api:ro" \
  api python -m pytest -p no:cacheprovider tests -q
```

### 3.4 Run the AI spike tests safely

Run them in a sealed container with no network, and deselect the one test that
writes to a database:

```bash
docker run --rm --network none \
  -v "$PWD/spikes:/app/spikes:ro" -v "$PWD/services/api:/app/services/api:ro" \
  -e PYTHONDONTWRITEBYTECODE=1 -e PYTHONPATH=/app/services/api:/app \
  -e DATABASE_URL="postgresql+psycopg://nobody:none@unreachable.invalid:5432/none" \
  -e SECRET_KEY=sealed -e AGENT_ENABLED=false -w /app kitchen-copilot-api \
  python -m pytest -p no:cacheprovider -q \
  spikes/ai/test_spikes.py spikes/ai/test_gemini_retry.py \
  --deselect spikes/ai/test_spikes.py::test_pgvector_retrieval_respects_campus
```

No Gemini request is possible because the container has no network.

To include the database test as well, give it a disposable database on a
private Docker network without internet access. `--tmpfs` keeps that database
in memory, so no Docker volume is created:

```bash
PW=$(openssl rand -hex 16)
docker network create --internal kc-spike-net
docker run -d --name kc-spike-db --network kc-spike-net \
  --tmpfs /var/lib/postgresql/data \
  -e POSTGRES_PASSWORD="$PW" -e POSTGRES_DB=spike_isolated pgvector/pgvector:pg16
until docker exec kc-spike-db pg_isready -U postgres -h 127.0.0.1 >/dev/null 2>&1; do
  sleep 1
done

docker run --rm --network kc-spike-net \
  -v "$PWD/spikes:/app/spikes:ro" -v "$PWD/services/api:/app/services/api:ro" \
  -e PYTHONDONTWRITEBYTECODE=1 -e PYTHONPATH=/app/services/api:/app \
  -e DATABASE_URL="postgresql+psycopg://postgres:$PW@kc-spike-db:5432/spike_isolated" \
  -e SECRET_KEY=sealed -e AGENT_ENABLED=false -w /app kitchen-copilot-api \
  python -m pytest -p no:cacheprovider -q \
  spikes/ai/test_spikes.py spikes/ai/test_gemini_retry.py

docker rm -f kc-spike-db
docker network rm kc-spike-net
unset PW
```

### 3.5 Frontend checks (no database involved)

```bash
cd apps/web
npx tsc --noEmit
npm run lint
```

### 3.6 Regenerate the frontend API types

Review the backend API changes first.

Port 8000 is the developer's own API (`uvicorn --reload` from the working
tree since 18 November 2026; the Docker `api` container stays stopped), so
it serves the working-tree code. Use it as the source when it is running
and has reloaded after the last backend change (if the Docker `api`
container is ever used instead, it serves the code its image was built
from):

```bash
cd apps/web
npm run generate:api-types
npx tsc --noEmit
```

Otherwise, generate the schema from the working tree in a sealed container
(no network, no database), which matches what CI does:

```bash
docker run --rm --network none -v "$PWD/services/api:/app/services/api:ro" \
  -e PYTHONDONTWRITEBYTECODE=1 -e PYTHONPATH=/app/services/api \
  -e DATABASE_URL="postgresql+psycopg://nobody:none@unreachable.invalid:5432/none" \
  -e SECRET_KEY=sealed -e AGENT_ENABLED=false -w /app kitchen-copilot-api \
  python -c "import json; from app.main import app; print(json.dumps(app.openapi()))" \
  > /tmp/kitchen-copilot-openapi.json
cd apps/web
npx openapi-typescript /tmp/kitchen-copilot-openapi.json -o src/types/api.ts
npx tsc --noEmit
```

CI fails if `src/types/api.ts` differs from the generated output.

## 4. Backups

Store backups **outside** the repository, readable only by your user.

### 4.1 Back up the Docker application database

```bash
B="$HOME/kitchen-copilot-backups/$(date +%Y%m%d-%H%M%S)"
mkdir -p "$B" && chmod 700 "$B"
docker compose exec -T db pg_dump -U kitchen -d kitchen_copilot_db -Fc \
  > "$B/docker_kitchen_copilot_db.dump"
```

### 4.2 Back up the host (Homebrew) database

`pg_dump` only reads. Supply the password interactively or through
`~/.pgpass`; never paste it into a script that is committed.

```bash
pg_dump -h localhost -p 5432 -U postgres -d kitchen_copilot_db -Fc \
  -f "$B/homebrew_kitchen_copilot_db.dump"
```

### 4.3 Verify a backup without touching any real server

Restore into a temporary, network-isolated container and compare row counts.
`--tmpfs` keeps the restored data in memory, so no Docker volume is created.

```bash
docker run -d --name kc-restore-check --network none \
  --tmpfs /var/lib/postgresql/data \
  -e POSTGRES_PASSWORD="$(openssl rand -hex 16)" pgvector/pgvector:pg16

# Wait until initialisation has finished. TCP connections are accepted only by
# the final server, not by the temporary one used during initialisation.
until docker exec kc-restore-check pg_isready -U postgres -h 127.0.0.1 >/dev/null 2>&1; do
  sleep 1
done

docker exec kc-restore-check psql -U postgres -c "create database scratch_restore"
docker exec -i kc-restore-check pg_restore -U postgres -d scratch_restore \
  --no-owner --no-privileges --exit-on-error < "$B/docker_kitchen_copilot_db.dump"
```

Compare `select count(*)` for every table between the source and
`scratch_restore`. Record the result, then remove the temporary container:

```bash
docker rm -f kc-restore-check
```

### 4.4 When a backup is mandatory

- Before every migration on any database that holds real records.
- Before rehearsing a risky migration (enum changes, data backfills,
  meal-session normalization, constraint relaxations).
- Before any bulk data import.

## 5. Working-tree safety

Before large changes, copy uncommitted work outside the repository:

```bash
B="$HOME/kitchen-copilot-backups/worktree-$(date +%Y%m%d-%H%M%S)"
mkdir -p "$B"
git diff --binary > "$B/tracked-changes.patch"
( git diff --name-only; git ls-files --others --exclude-standard ) | sort -u \
  > "$B/files.txt"
tar -czf "$B/files.tar.gz" -T "$B/files.txt"
```

Do not use `git reset --hard`, `git checkout -- .`, `git clean` or
`git stash` on uncommitted work that has not been backed up.

## 6. Schema changes while the port 8000 API is running

The developer's API on port 8000 runs from the working tree with
`--reload`: saving any `.py` file under `services/api` restarts it on the
new code at once. Code that needs a new migration must therefore not be
saved into the working tree before that migration is applied to the
development database, and must be saved immediately after it.

Procedure (used from Stage 4 slice 4a onwards):

1. Copy `services/api` (without `.venv` and `.env*`) to a scratch folder and
   write the backend change and its migration there.
2. Run the tests and the migration round trip against that copy (mounted
   read-only into the test container and the throwaway server).
3. Apply the migration (section 4.4 backup first).
4. Sync the changed files into the working tree with a script that refuses
   to copy anything except the expected file list, keeps the replaced
   versions, and reports success explicitly. A script that ends without
   printing its success line has failed, whatever its exit status shows.
5. Check that port 8000 serves the new code, then run the smoke test.

### 6.1 Incident log

**23 November 2026, about 10:08–10:09:39 (IST) — model ahead of the
database.** While starting slice 4a, the four new stock-ledger columns were
added to `StockMovement` in the working tree (`app/models/purchases.py`)
before migration `b5e1d7c3a920` existed on the development database. The
port 8000 API reloaded onto that model, so any request reading stock
movements (stock log, receipt detail, dashboard, receipt acceptance) would
have failed with a database error for about a minute and a half.
Correction: the three edits were reverted at once; the file was confirmed
back to its previous content (no stock-ledger lines in its diff against
the last commit) and `/health` answered 200; all further backend work was
done in a scratch copy (procedure above). Data impact: none. The
development database recorded no inserted, updated or deleted rows between
its last restart and the pre-migration snapshot at 11:06, which covers
this window.

**23 November 2026, 11:06:32–11:07:30 (IST) — code behind the database.**
Migration `b5e1d7c3a920` was applied at 11:06:21–11:06:32. The script that
then copies the slice-4a code into the working tree stopped silently: it
compared the folders with `diff`, which exits with status 1 when files
differ, and under `set -e -o pipefail` that ended the script before it
copied anything. For about a minute the port 8000 API ran the previous code
on the new schema; reads were unaffected, but accepting a goods receipt
would have failed (the new columns are required). Correction: the
comparison was changed to `{ diff ... || true; }`, the file-list guard was
rerun, the 14 expected files were synced at 11:07:30 (previous versions
kept), the working tree was confirmed identical to the verified code, the
new routes were confirmed live on port 8000, and the smoke tests passed
(stock 23 of 23, Stage 3 54 of 54). Data impact: none. The only rows
written in application tables since the migration are its own (6 receipt
movements backfilled, 1 revision row); the write counters were identical
after the smoke tests.

### 6.2 The append-only stock ledger (from migration `c7d2e9f4a816`)

`stock_movements` refuses `UPDATE`, `DELETE` and `TRUNCATE` through two
database triggers, for every role including the `kitchen` superuser, and
every application session refuses to change or delete a movement
(`app/models/ledger_guard.py`). Corrections are REVERSAL movements.

- A test that needs a movement with particular values inserts it with those
  values; it never edits one (see `test_stock_log_days_are_campus_local`).
- A future migration that must change existing movement rows needs its own
  approval, and must disable and re-enable the triggers explicitly inside
  the migration (`ALTER TABLE stock_movements DISABLE TRIGGER
  stock_movements_no_update_delete` … `ENABLE TRIGGER …`).
- Test databases get the same triggers whenever SQLAlchemy creates the
  table, so tests run against the production rule. Dropping test tables
  (`drop_all`) is not affected.
- Migration `0e7d99065bd3` (slice 4c) left both triggers and their function
  unchanged; its verification compares their definitions before and after
  the upgrade, the downgrade and the re-upgrade. Later migrations should do
  the same.
- Saved stock counts (`stock_counts`, `stock_count_items`, slice 4c) are
  never changed either, but only the application guard enforces it; there
  is no database trigger on those tables (one would need its own approval).
  A test or script never edits a saved count; it records a new one.
- Migration `ea00e5387c2f` (Stage 5 meals) also left both triggers and their
  function unchanged (checked after the upgrade, the downgrade and the
  re-upgrade, and on the development database before and after the apply).
- Meal dishes and leftovers reference each other once retained food is
  carried forward. The SQLite test fixture therefore switches foreign-key
  checks off before dropping its tables, and the database-level lock on a
  carried source is tested on PostgreSQL, where the migration creates it.

### 6.3 Final portion standards and meal plans (from migration `f3a8c2d61b47`)

Stage 6 (meal planning, migration M4) adds four row triggers, for every role
including the `kitchen` superuser (safeguard S6-2):

- `portion_standards_final`: a standard is never deleted, and an APPROVED or
  CANCELLED one never changes. A wrong approved standard is replaced by
  approving a newer version, not by editing it.
- `portion_standard_basis_final`: the meal records behind a suggested
  standard are added only to a draft and never changed or deleted.
- `meal_plans_final`: a plan is never deleted; a CANCELLED plan never
  changes; an APPROVED plan may only become CANCELLED (status, cancellation
  fields and `updated_at` only); approval needs every line's snapshot.
- `meal_plan_lines_final`: lines change only while their plan is a DRAFT.

Consequences for tests and scripts:

- Code that approves a plan writes the line snapshots and flushes them
  before changing the plan's status (the lines trigger reads the plan's
  status).
- A test or script never edits an approved standard or plan; it creates a
  new version or a new plan. Test databases get the same triggers whenever
  SQLAlchemy creates the tables (PostgreSQL and SQLite), so tests run against
  the production rule. Dropping test tables (`drop_all`) is not affected.
- A future migration that must change existing planning rows needs its own
  approval and must disable and re-enable the trigger explicitly. The M4
  verification did that only on the throwaway server, to remove a draft it
  had inserted to test the downgrade guard.
- Migration `f3a8c2d61b47` adds the nullable `items.item_kind` column. A
  table fingerprint that compares rows as whole-row text (`t::text`) changes
  when a column is added even if no value changes, so the M4 checks compare
  every pre-existing table over its pre-M4 columns, and check separately that
  no item was classified by the migration.
- Migration `f3a8c2d61b47` left the two stock ledger triggers and their
  function unchanged (checked on the throwaway server after the upgrade, the
  downgrade and the re-upgrade, and on the development database before and
  after the apply).
- Long test runs on the laptop: the PostgreSQL suite and the browser
  suites take 15–50 minutes under load. If the Mac idle-sleeps during a run
  (on 24 November 2026 it slept for 35 minutes on battery), a test's
  30-minute access token expires between two requests and the test fails
  with "Not authenticated". Run long suites under `caffeinate -i` (it only
  prevents idle sleep while the command runs). Do not lengthen token
  lifetimes or change authentication to work around it.

### 6.4 Outsourced food and received meal-dish lines (from migration `b8e4c2a9d175`)

Stage 8a (migration M6) adds the four outsourced tables and two
`meal_dishes` columns, and widens three meal-dish checks:

- A "received" meal-dish line has `output_quantity = 0`,
  `carried_quantity = 0`, `received_quantity > 0` and a
  `source_delivery_line_id`; a composite foreign key ties it to the delivery
  line's id, accepted quantity, unit and campus. While it exists the
  database refuses to change or delete that delivery line. Prepared and
  carried lines keep their old rules (`received_quantity = 0`, no source
  delivery line).
- Outsourced food never enters the stock ledger: `stock_ledger.post` refuses
  any non-reversal posting for an OUTSOURCED item (the item rows are locked
  first), and goods-receipt acceptance locks and checks its items. A script
  or test must never post stock for an OUTSOURCED item, and an item with
  stock movements cannot be classified OUTSOURCED.
- The downgrade refuses while any outsourced order or received meal-dish
  line exists; restore the pre-migration backup instead.
- M6 writes no module, permission or grant: the existing
  `outsourced_food.*` codes are used. The apply checks therefore compare
  every pre-existing table (modules, permissions and grants included) over
  its pre-M6 columns (`meal_dishes` without the two new columns).
- Lock order in the outsourced code: delivery, order, meal session, meal
  record. Creating a meal record locks its meal session row too, so a
  delivery confirmed at the same moment is never left waiting.

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

The running `api` container (port 8000) serves the code its image was built
from. Use it as the source only when the backend has not changed since that
build:

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

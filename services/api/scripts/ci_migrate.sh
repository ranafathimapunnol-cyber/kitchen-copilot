#!/usr/bin/env bash
# Migrate a FRESH, EMPTY, DISPOSABLE test database (GitHub Actions service
# container, or a throwaway local container) from base to head.
#
# Three migrations carry an authorization guard, because the API container
# runs "alembic upgrade head" at start and must never apply them to a
# database with real records by accident:
#   d5e8f0b2a314 (M1) needs KC_AUTHORIZE_M1=d5e8f0b2a314
#   e2b7c4d9a5f1 (M2) needs KC_AUTHORIZE_MIGRATION=e2b7c4d9a5f1
#   a7d3e9b1c4f2 (M3) needs KC_AUTHORIZE_MIGRATION=a7d3e9b1c4f2
# M2 and M3 share one variable that must equal the revision being applied,
# so no single "alembic upgrade head" can pass both. This script first proves
# the guards still refuse, then applies each guarded revision on its own with
# its exact variable set for that one command only.
#
# Safety: it refuses unless (1) it runs in CI (CI=true, set by GitHub
# Actions) or KC_DISPOSABLE_DATABASE=yes is given explicitly, (2) DATABASE_URL
# is set in the environment (never taken from a .env file), and (3) the target
# database has no tables at all. It is not a tool for real databases.
set -euo pipefail
cd "$(dirname "$0")/.."

unset KC_AUTHORIZE_M1 KC_AUTHORIZE_MIGRATION

if [ "${CI:-}" != "true" ] && [ "${KC_DISPOSABLE_DATABASE:-}" != "yes" ]; then
  echo "Refusing: not in CI. For a throwaway local database set KC_DISPOSABLE_DATABASE=yes." >&2
  exit 1
fi
if [ -z "${DATABASE_URL:-}" ]; then
  echo "Refusing: DATABASE_URL must be set explicitly (a .env file is never used here)." >&2
  exit 1
fi
tables=$(python - <<'PY'
import os
from sqlalchemy import create_engine, inspect
engine = create_engine(os.environ["DATABASE_URL"])
print(len(inspect(engine).get_table_names()))
engine.dispose()
PY
)
if [ "$tables" != "0" ]; then
  echo "Refusing: the target database already has $tables table(s); this script is for an empty CI database." >&2
  exit 1
fi

expect_refusal() {
  # $1 = description; rest = command. Passes only if the command fails with
  # the guard's "is not authorized" message.
  local what="$1"; shift
  local out
  if out=$("$@" 2>&1); then
    echo "FAIL: $what succeeded without authorization" >&2
    exit 1
  fi
  if ! grep -q "is not authorized" <<<"$out"; then
    echo "FAIL: $what failed for another reason:" >&2
    echo "$out" | tail -20 >&2
    exit 1
  fi
  echo "ok: $what refused (not authorized)"
}

current() { alembic current 2>/dev/null | awk '{print $1}' | head -1; }

if [ -n "$(current)" ]; then
  echo "Refusing: the database already has migration revision $(current); this script is for an empty CI database." >&2
  exit 1
fi

# 1. The guards refuse without (or with the wrong) authorization, and nothing
#    is left half-applied.
expect_refusal "M1 without KC_AUTHORIZE_M1" alembic upgrade head
expect_refusal "M1 with a wrong KC_AUTHORIZE_M1" env KC_AUTHORIZE_M1=wrong alembic upgrade head
[ -z "$(current)" ] || { echo "FAIL: a refused M1 left revision $(current) behind" >&2; exit 1; }
echo "ok: refused M1 left the database empty (rolled back)"

alembic upgrade c4d7e9a1f203
KC_AUTHORIZE_M1=d5e8f0b2a314 alembic upgrade d5e8f0b2a314
expect_refusal "M2 without KC_AUTHORIZE_MIGRATION" alembic upgrade e2b7c4d9a5f1
expect_refusal "M2 with M3's value" env KC_AUTHORIZE_MIGRATION=a7d3e9b1c4f2 alembic upgrade e2b7c4d9a5f1
[ "$(current)" = "d5e8f0b2a314" ] || { echo "FAIL: revision moved after a refused M2" >&2; exit 1; }

KC_AUTHORIZE_MIGRATION=e2b7c4d9a5f1 alembic upgrade e2b7c4d9a5f1
expect_refusal "M3 without KC_AUTHORIZE_MIGRATION" alembic upgrade a7d3e9b1c4f2
expect_refusal "M3 with M2's value" env KC_AUTHORIZE_MIGRATION=e2b7c4d9a5f1 alembic upgrade a7d3e9b1c4f2
[ "$(current)" = "e2b7c4d9a5f1" ] || { echo "FAIL: revision moved after a refused M3" >&2; exit 1; }

# 2. Authorized, one guarded revision at a time, then any later unguarded ones.
KC_AUTHORIZE_MIGRATION=a7d3e9b1c4f2 alembic upgrade a7d3e9b1c4f2
alembic upgrade head

head=$(alembic heads | awk '{print $1}' | head -1)
[ "$(current)" = "$head" ] || { echo "FAIL: at $(current), expected head $head" >&2; exit 1; }
echo "migrated empty database to head $head"

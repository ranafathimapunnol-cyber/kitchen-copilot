"""The stock ledger is append-only (decision 4b-5, approved 23 November 2026),
and a saved stock count is never changed (STK05, slice 4c; section 3 below).

Two independent layers:

1. Database triggers on ``stock_movements`` refuse every UPDATE and DELETE
   (row level) and TRUNCATE (statement level, PostgreSQL). Migration
   b5e1d7c3a920's successor (M2b) installs them on existing databases; the
   DDL below installs the same triggers whenever SQLAlchemy creates the
   table (test databases), so tests run against the production rule.
2. An application guard on every ORM session refuses to flush a changed or
   deleted ``StockMovement`` and refuses ORM bulk UPDATE or DELETE
   statements on the table.

Corrections are REVERSAL movements, never edits. A migration that must
change existing movement rows has to disable and re-enable the triggers
explicitly (``ALTER TABLE stock_movements DISABLE TRIGGER ...``) and needs
its own approval.
"""

from sqlalchemy import DDL, event
from sqlalchemy.orm import Session

from app.models.purchases import StockMovement

APPEND_ONLY_MESSAGE = (
    "Stock movements are append-only: post a reversal instead of changing "
    "or deleting a movement."
)

# ---------- 1. database triggers (also used by migration M2b) ----------

PG_FUNCTION = """
CREATE OR REPLACE FUNCTION stock_movements_append_only() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION USING
        MESSAGE = 'stock_movements is append-only: ' || TG_OP
                  || ' is not allowed; post a reversal instead',
        HINT = 'Corrections are REVERSAL movements (decision 4b-5).';
END;
$$
"""
PG_ROW_TRIGGER = """
CREATE TRIGGER stock_movements_no_update_delete
BEFORE UPDATE OR DELETE ON stock_movements
FOR EACH ROW EXECUTE FUNCTION stock_movements_append_only()
"""
PG_TRUNCATE_TRIGGER = """
CREATE TRIGGER stock_movements_no_truncate
BEFORE TRUNCATE ON stock_movements
FOR EACH STATEMENT EXECUTE FUNCTION stock_movements_append_only()
"""
SQLITE_TRIGGERS = (
    """
    CREATE TRIGGER stock_movements_no_update BEFORE UPDATE ON stock_movements
    BEGIN SELECT RAISE(ABORT, 'stock_movements is append-only: UPDATE is not allowed; post a reversal instead'); END
    """,
    """
    CREATE TRIGGER stock_movements_no_delete BEFORE DELETE ON stock_movements
    BEGIN SELECT RAISE(ABORT, 'stock_movements is append-only: DELETE is not allowed; post a reversal instead'); END
    """,
)

table = StockMovement.__table__
for statement in (PG_FUNCTION, PG_ROW_TRIGGER, PG_TRUNCATE_TRIGGER):
    event.listen(table, "after_create", DDL(statement).execute_if(dialect="postgresql"))
for statement in SQLITE_TRIGGERS:
    event.listen(table, "after_create", DDL(statement).execute_if(dialect="sqlite"))


# ---------- 2. application guard on every ORM session ----------

class LedgerIsAppendOnly(RuntimeError):
    pass


@event.listens_for(Session, "before_flush")
def _refuse_changed_movements(session, _flush_context, _instances):
    for obj in session.deleted:
        if isinstance(obj, StockMovement):
            raise LedgerIsAppendOnly(APPEND_ONLY_MESSAGE)
    for obj in session.dirty:
        if isinstance(obj, StockMovement) and session.is_modified(obj, include_collections=False):
            raise LedgerIsAppendOnly(APPEND_ONLY_MESSAGE)


@event.listens_for(Session, "do_orm_execute")
def _refuse_bulk_changes(state):
    if state.is_update or state.is_delete:
        target = getattr(state.statement, "table", None)
        if getattr(target, "name", None) == StockMovement.__tablename__:
            raise LedgerIsAppendOnly(APPEND_ONLY_MESSAGE)


# ---------- 3. a saved stock count is never changed (STK05, slice 4c) ----------
#
# STK05 criterion 3: "The original count must remain unchanged." No endpoint
# edits or deletes a count; this application guard refuses it for any other
# code path too. (Database level protection for counts is not installed: it
# would be a new trigger needing its own approval.)

from app.models.stock import StockCount, StockCountItem  # noqa: E402

COUNT_IS_FINAL_MESSAGE = (
    "A saved stock count is never changed (STK05): record a new count instead."
)
FINAL_COUNT_TYPES = (StockCount, StockCountItem)
FINAL_COUNT_TABLES = frozenset(model.__tablename__ for model in FINAL_COUNT_TYPES)


class CountIsFinal(RuntimeError):
    pass


@event.listens_for(Session, "before_flush")
def _refuse_changed_counts(session, _flush_context, _instances):
    for obj in session.deleted:
        if isinstance(obj, FINAL_COUNT_TYPES):
            raise CountIsFinal(COUNT_IS_FINAL_MESSAGE)
    for obj in session.dirty:
        if isinstance(obj, FINAL_COUNT_TYPES) and session.is_modified(obj, include_collections=False):
            raise CountIsFinal(COUNT_IS_FINAL_MESSAGE)


@event.listens_for(Session, "do_orm_execute")
def _refuse_bulk_count_changes(state):
    if state.is_update or state.is_delete:
        target = getattr(state.statement, "table", None)
        if getattr(target, "name", None) in FINAL_COUNT_TABLES:
            raise CountIsFinal(COUNT_IS_FINAL_MESSAGE)

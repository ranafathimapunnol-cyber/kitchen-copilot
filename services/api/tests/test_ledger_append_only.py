"""
The stock ledger is append-only (decision 4b-5, approved 23 November 2026):
- the application refuses to flush a changed or deleted StockMovement and
  refuses ORM bulk UPDATE or DELETE statements on the table;
- the database refuses UPDATE and DELETE (and TRUNCATE on PostgreSQL) even
  for SQL sent directly, past the application.
Inserting, and correcting by reversal, keep working.

In-memory SQLite with the shared fixtures of test_operational_authority;
the PostgreSQL triggers are tested in tests/test_kitchen_issues_postgres.py.
"""

from datetime import datetime, timezone
from decimal import Decimal

import pytest
from sqlalchemy import delete, text, update
from sqlalchemy.exc import DBAPIError

from app.models.ledger_guard import LedgerIsAppendOnly
from app.models.purchases import StockMovement

from tests.test_operational_authority import (  # noqa: F401 (fixtures)
    act_as,
    client,
    db,
    world,
)


@pytest.fixture
def movement(db, world):
    a = world.a
    row = StockMovement(campus_id=a.campus.id, item_id=a.item.id, movement_type="RECEIPT", direction=1,
                        quantity=Decimal("5"), unit_id=a.kg.id, reference_type="TEST", reference_id=1,
                        source_key="TEST:append-only", effective_at=datetime.now(timezone.utc),
                        created_by=a.admin.id)
    db.add(row)
    db.commit()
    return row


def unchanged(db, movement_id):
    db.expire_all()
    row = db.get(StockMovement, movement_id)
    return row is not None and row.quantity == Decimal("5.000") and row.remarks is None


def test_the_application_refuses_to_change_a_movement(db, movement):
    movement.quantity = Decimal("50")
    with pytest.raises(LedgerIsAppendOnly):
        db.commit()
    db.rollback()
    assert unchanged(db, movement.id)


def test_the_application_refuses_to_delete_a_movement(db, movement):
    db.delete(movement)
    with pytest.raises(LedgerIsAppendOnly):
        db.commit()
    db.rollback()
    assert unchanged(db, movement.id)


@pytest.mark.parametrize("statement", [
    lambda: update(StockMovement).values(remarks="edited"),
    lambda: delete(StockMovement),
])
def test_the_application_refuses_bulk_changes(db, movement, statement):
    with pytest.raises(LedgerIsAppendOnly):
        db.execute(statement())
    db.rollback()
    assert unchanged(db, movement.id)


def test_query_update_and_delete_are_refused_too(db, movement):
    with pytest.raises(LedgerIsAppendOnly):
        db.query(StockMovement).filter_by(id=movement.id).update({"remarks": "edited"})
    db.rollback()
    with pytest.raises(LedgerIsAppendOnly):
        db.query(StockMovement).filter_by(id=movement.id).delete()
    db.rollback()
    assert unchanged(db, movement.id)


@pytest.mark.parametrize("sql", [
    "UPDATE stock_movements SET remarks = 'edited'",
    "UPDATE stock_movements SET quantity = 50, direction = -1",
    "DELETE FROM stock_movements",
])
def test_the_database_refuses_direct_sql(db, movement, sql):
    """Raw SQL bypasses the application guard; the trigger still refuses."""
    with pytest.raises(DBAPIError) as refused:
        db.execute(text(sql))
    assert "append-only" in str(refused.value)
    db.rollback()
    assert unchanged(db, movement.id)


def test_inserting_and_reversing_still_work(client, db, world, movement):
    a = world.a
    act_as(client, a.admin)
    opening = client.post("/api/stock/openings", json={
        "effective_date": "2026-11-01", "lines": [{"item_id": a.item.id, "quantity": "3"}]}).json()["items"][0]
    assert client.post(f"/api/stock/openings/{opening['id']}/reverse", json={"reason": "append only"}).status_code == 200
    assert db.query(StockMovement).count() == 3
    assert unchanged(db, movement.id)

"""Outsourced food never enters raw-ingredient stock (Stage 8a; OUT01
criterion 7; project decisions P8-2 and P8-5).

An item classified OUTSOURCED is received through outsourced deliveries,
never through goods receipts, and has no stock balance: no opening stock,
kitchen issue, unused return, count or adjustment. These helpers give the
stock screens one refusal and one message.
"""

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.models.master_data import Item

OUTSOURCED = "OUTSOURCED"


def outsourced_message(names: list[str], action: str) -> str:
    listed = ", ".join(sorted(names))
    noun = "is" if len(names) == 1 else "are"
    return (
        f"{listed} {noun} outsourced food, which never enters raw-ingredient stock, so it cannot be {action}. "
        "Outsourced food is ordered and received under Outsourced Food."
    )


def refuse_outsourced(db: Session, campus_id: int, item_ids, action: str, lock: bool = False) -> None:
    """422 when any of the items is OUTSOURCED. With lock=True the item rows
    are locked (FOR NO KEY UPDATE, in id order) so a classification cannot
    change between this check and the caller's commit; PUT /api/items/{id}/kind
    takes the same lock."""
    ids = sorted({int(i) for i in item_ids if i is not None})
    if not ids:
        return
    query = db.query(Item).filter(Item.campus_id == campus_id, Item.id.in_(ids)).order_by(Item.id)
    if lock:
        query = query.with_for_update(key_share=True)
    names = [item.name for item in query.all() if item.item_kind == OUTSOURCED]
    if names:
        raise HTTPException(status_code=422, detail=outsourced_message(names, action))


def not_outsourced(column):
    """SQL filter for stock pickers: items that are not OUTSOURCED (NULL,
    RAW and PREPARED stay selectable)."""
    return (column.is_(None)) | (column != OUTSOURCED)

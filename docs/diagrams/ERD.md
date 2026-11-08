# Kitchen Copilot — Entity Relationship Diagram

This diagram reflects the registered SQLAlchemy models and the
database schema migrated through revision `fb84dd6fb038`.

```mermaid
erDiagram
    CAMPUS ||--o{ USER : has
    CAMPUS ||--o{ AUDIT_LOG : scopes
    CAMPUS ||--o{ CATEGORY : has
    CAMPUS ||--o{ UNIT : has
    CAMPUS ||--o{ UNIT_CONVERSION : has
    CAMPUS ||--o{ ITEM : has
    CAMPUS ||--o{ SUPPLIER : has
    CAMPUS ||--o{ MEAL_SESSION : has
    CAMPUS ||--o{ MENU : has
    CAMPUS ||--o{ MENU_MAIN_ITEM : has
    CAMPUS ||--o{ PURCHASE : has
    CAMPUS ||--o{ PURCHASE_ITEM : has
    CAMPUS ||--o{ GOODS_RECEIPT : has
    CAMPUS ||--o{ GOODS_RECEIPT_ITEM : has
    CAMPUS ||--o{ STOCK_MOVEMENT : has
    CAMPUS ||--o{ SUPPLIER_PAYMENT : has
    CAMPUS ||--o{ SUPPLIER_RETURN : has
    CAMPUS ||--o{ SUPPLIER_RETURN_ITEM : has

    USER ||--o{ AUDIT_LOG : performs
    USER ||--o{ PURCHASE : creates
    USER ||--o{ GOODS_RECEIPT : creates
    USER ||--o{ GOODS_RECEIPT : accepts
    USER ||--o{ STOCK_MOVEMENT : records
    USER ||--o{ SUPPLIER_PAYMENT : records
    USER ||--o{ SUPPLIER_RETURN : creates

    CATEGORY ||--o{ ITEM : classifies
    UNIT ||--o{ ITEM : base_unit
    UNIT ||--o{ UNIT_CONVERSION : source_unit
    UNIT ||--o{ UNIT_CONVERSION : target_unit
    UNIT ||--o{ PURCHASE_ITEM : purchase_unit
    UNIT ||--o{ MENU_MAIN_ITEM : portion_unit
    UNIT ||--o{ STOCK_MOVEMENT : movement_unit

    MEAL_SESSION ||--o{ MENU : schedules
    MENU ||--o{ MENU_MAIN_ITEM : contains
    ITEM ||--o{ MENU_MAIN_ITEM : used_in

    SUPPLIER ||--o{ PURCHASE : supplies
    PURCHASE ||--|{ PURCHASE_ITEM : contains
    PURCHASE ||--o{ GOODS_RECEIPT : receives
    PURCHASE ||--o{ SUPPLIER_PAYMENT : has
    PURCHASE ||--o{ SUPPLIER_RETURN : has

    GOODS_RECEIPT ||--|{ GOODS_RECEIPT_ITEM : contains
    PURCHASE_ITEM ||--o{ GOODS_RECEIPT_ITEM : received_against
    PURCHASE_ITEM ||--o{ SUPPLIER_RETURN_ITEM : returned_against
    SUPPLIER_RETURN ||--|{ SUPPLIER_RETURN_ITEM : contains

    ITEM ||--o{ STOCK_MOVEMENT : tracks
    GOODS_RECEIPT_ITEM ||--o| STOCK_MOVEMENT : generates

"""add item kind, portion standards, meal plans and planning permissions (Stage 6, migration M4)

Revision ID: f3a8c2d61b47
Revises: ea00e5387c2f

Approved 24 November 2026 (docs/STAGE-6-PLANNING-PLAN.md, decisions 6-1 to
6-9, safeguards S6-1 to S6-6 and the section 12 choices).

1. items.item_kind: nullable, RAW, PREPARED or OUTSOURCED (check). Existing
   items stay NULL ("not classified"); nothing is backfilled.
2. portion_standards: versioned per-person quantities per menu and item with
   an effective date; DRAFT, APPROVED or CANCELLED; an approved version has
   its version number, approver and the item kind it was approved with.
3. portion_standard_basis: the closed meal records behind a suggested
   standard (PLAN03).
4. meal_plans: one live plan per campus, date and meal session (partial
   unique index), MP-numbered; meal_plan_lines: the main items, optional
   one-day overrides with a reason, and the snapshot written at approval.
5. Triggers (S6-2): approved and cancelled standards, basis rows, approved
   and cancelled plans and the lines of a plan that is not a draft refuse
   UPDATE and DELETE; an approved plan may only become CANCELLED.
6. Permission modules `portion_standard` and `meal_plan` (create, read,
   update; permission rows only). No grant is inserted, changed or
   deactivated.

Additive: no existing row changes; menu_main_items, stock_movements and its
append-only triggers are not touched. The downgrade refuses while plans,
standards, classified items or grants on the new codes exist.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "f3a8c2d61b47"
down_revision: Union[str, Sequence[str], None] = "ea00e5387c2f"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

MODULES = (("portion_standard", "Portion Standards"), ("meal_plan", "Meal Plans"))
ACTIONS = ("CREATE", "READ", "UPDATE")

# Frozen copies of the trigger SQL in app/models/planning.py.
GUARDS = (
    """
CREATE OR REPLACE FUNCTION portion_standards_guard() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    IF TG_OP = 'DELETE' THEN
        RAISE EXCEPTION USING
            MESSAGE = 'portion_standards: a standard is never deleted; cancel a draft instead',
            HINT = 'Stage 6 safeguard S6-2.';
    END IF;
    IF OLD.status <> 'DRAFT' THEN
        RAISE EXCEPTION USING
            MESSAGE = 'portion_standards: an approved or cancelled standard cannot be changed',
            HINT = 'Approve a newer version instead (Stage 6 safeguard S6-2).';
    END IF;
    RETURN NEW;
END;
$$
""",
    """
CREATE TRIGGER portion_standards_final
BEFORE UPDATE OR DELETE ON portion_standards
FOR EACH ROW EXECUTE FUNCTION portion_standards_guard()
""",
    """
CREATE OR REPLACE FUNCTION portion_standard_basis_guard() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    IF TG_OP <> 'INSERT' THEN
        RAISE EXCEPTION USING
            MESSAGE = 'portion_standard_basis: suggestion basis rows are never changed or deleted',
            HINT = 'Stage 6 safeguard S6-2.';
    END IF;
    IF (SELECT status FROM portion_standards WHERE id = NEW.standard_id) IS DISTINCT FROM 'DRAFT' THEN
        RAISE EXCEPTION USING
            MESSAGE = 'portion_standard_basis: basis rows are added only to a draft standard',
            HINT = 'Stage 6 safeguard S6-2.';
    END IF;
    RETURN NEW;
END;
$$
""",
    """
CREATE TRIGGER portion_standard_basis_final
BEFORE INSERT OR UPDATE OR DELETE ON portion_standard_basis
FOR EACH ROW EXECUTE FUNCTION portion_standard_basis_guard()
""",
    """
CREATE OR REPLACE FUNCTION meal_plans_guard() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    IF TG_OP = 'DELETE' THEN
        RAISE EXCEPTION USING
            MESSAGE = 'meal_plans: a plan is never deleted; cancel it instead',
            HINT = 'Stage 6 safeguard S6-2.';
    END IF;
    IF OLD.status = 'CANCELLED' THEN
        RAISE EXCEPTION USING
            MESSAGE = 'meal_plans: a cancelled plan cannot be changed',
            HINT = 'Stage 6 safeguard S6-2.';
    END IF;
    IF OLD.status = 'APPROVED' AND (
        NEW.status <> 'CANCELLED'
        OR (to_jsonb(NEW) - ARRAY['status', 'cancelled_by', 'cancelled_at', 'cancellation_reason', 'updated_at'])
           IS DISTINCT FROM
           (to_jsonb(OLD) - ARRAY['status', 'cancelled_by', 'cancelled_at', 'cancellation_reason', 'updated_at'])
    ) THEN
        RAISE EXCEPTION USING
            MESSAGE = 'meal_plans: an approved plan cannot be changed; cancel it with a reason and create a new plan',
            HINT = 'Stage 6 safeguard S6-2 and decision 6-6.';
    END IF;
    IF OLD.status = 'DRAFT' AND NEW.status = 'APPROVED' AND (
        NOT EXISTS (SELECT 1 FROM meal_plan_lines WHERE plan_id = NEW.id)
        OR EXISTS (SELECT 1 FROM meal_plan_lines WHERE plan_id = NEW.id AND required_base_quantity IS NULL)
    ) THEN
        RAISE EXCEPTION USING
            MESSAGE = 'meal_plans: a plan is approved only with at least one line and every line''s snapshot',
            HINT = 'Stage 6 safeguard S6-2.';
    END IF;
    RETURN NEW;
END;
$$
""",
    """
CREATE TRIGGER meal_plans_final
BEFORE UPDATE OR DELETE ON meal_plans
FOR EACH ROW EXECUTE FUNCTION meal_plans_guard()
""",
    """
CREATE OR REPLACE FUNCTION meal_plan_lines_guard() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    IF TG_OP <> 'INSERT' AND (SELECT status FROM meal_plans WHERE id = OLD.plan_id) IS DISTINCT FROM 'DRAFT' THEN
        RAISE EXCEPTION USING
            MESSAGE = 'meal_plan_lines: lines change only while their plan is a draft',
            HINT = 'Stage 6 safeguard S6-2.';
    END IF;
    IF TG_OP <> 'DELETE' AND (SELECT status FROM meal_plans WHERE id = NEW.plan_id) IS DISTINCT FROM 'DRAFT' THEN
        RAISE EXCEPTION USING
            MESSAGE = 'meal_plan_lines: lines change only while their plan is a draft',
            HINT = 'Stage 6 safeguard S6-2.';
    END IF;
    IF TG_OP = 'DELETE' THEN
        RETURN OLD;
    END IF;
    RETURN NEW;
END;
$$
""",
    """
CREATE TRIGGER meal_plan_lines_final
BEFORE INSERT OR UPDATE OR DELETE ON meal_plan_lines
FOR EACH ROW EXECUTE FUNCTION meal_plan_lines_guard()
""",
)
TRIGGERS = (("meal_plan_lines_final", "meal_plan_lines", "meal_plan_lines_guard"),
            ("meal_plans_final", "meal_plans", "meal_plans_guard"),
            ("portion_standard_basis_final", "portion_standard_basis", "portion_standard_basis_guard"),
            ("portion_standards_final", "portion_standards", "portion_standards_guard"))

SNAPSHOT_COLUMNS = (
    "standard_id", "item_kind", "standard_quantity_per_person", "standard_unit_id", "quantity_per_person",
    "unit_id", "required_quantity", "rounded_up", "base_unit_id", "conversion_factor", "required_base_quantity",
)


def audit_columns():
    return [
        sa.Column("created_by", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("approved_by", sa.Integer(), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancelled_by", sa.Integer(), nullable=True),
        sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancellation_reason", sa.String(length=500), nullable=True),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"]),
        sa.ForeignKeyConstraint(["approved_by"], ["users.id"]),
        sa.ForeignKeyConstraint(["cancelled_by"], ["users.id"]),
    ]


CANCELLED_CHECK = (
    "(status = 'CANCELLED') = (cancelled_at IS NOT NULL) "
    "AND (cancelled_at IS NULL) = (cancelled_by IS NULL) "
    "AND (cancelled_at IS NULL) = (cancellation_reason IS NULL)"
)


def upgrade() -> None:
    # ---------- 1. item kind (6-8): nullable, no backfill ----------
    op.add_column("items", sa.Column("item_kind", sa.String(length=20), nullable=True))
    op.create_check_constraint("ck_item_kind", "items",
                               "item_kind IS NULL OR item_kind IN ('RAW', 'PREPARED', 'OUTSOURCED')")

    # ---------- 2. portion standards ----------
    op.create_table(
        "portion_standards",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("campus_id", sa.Integer(), nullable=False),
        sa.Column("menu_id", sa.Integer(), nullable=False),
        sa.Column("item_id", sa.Integer(), nullable=False),
        sa.Column("quantity_per_person", sa.Numeric(precision=18, scale=3), nullable=False),
        sa.Column("unit_id", sa.Integer(), nullable=False),
        sa.Column("effective_from", sa.Date(), nullable=False),
        sa.Column("version_no", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("source", sa.String(length=20), nullable=False),
        sa.Column("copied_from_menu_main_item_id", sa.Integer(), nullable=True),
        sa.Column("item_kind", sa.String(length=20), nullable=True),
        sa.Column("notes", sa.String(length=500), nullable=True),
        *audit_columns(),
        sa.ForeignKeyConstraint(["campus_id"], ["campuses.id"]),
        sa.ForeignKeyConstraint(["menu_id"], ["menus.id"]),
        sa.ForeignKeyConstraint(["item_id"], ["items.id"]),
        sa.ForeignKeyConstraint(["unit_id"], ["units.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("campus_id", "menu_id", "item_id", "version_no", name="uq_portion_standard_version"),
        sa.CheckConstraint("status IN ('DRAFT', 'APPROVED', 'CANCELLED')", name="ck_portion_standard_status"),
        sa.CheckConstraint("source IN ('MANUAL', 'COPIED', 'SUGGESTED')", name="ck_portion_standard_source"),
        sa.CheckConstraint("quantity_per_person > 0", name="ck_portion_standard_quantity"),
        sa.CheckConstraint("(source = 'COPIED') = (copied_from_menu_main_item_id IS NOT NULL)",
                           name="ck_portion_standard_copied"),
        sa.CheckConstraint(
            "(status = 'APPROVED') = (approved_at IS NOT NULL) "
            "AND (approved_at IS NULL) = (approved_by IS NULL) "
            "AND (approved_at IS NULL) = (version_no IS NULL) "
            "AND (approved_at IS NULL) = (item_kind IS NULL) "
            "AND (item_kind IS NULL OR item_kind IN ('RAW', 'PREPARED')) "
            "AND (version_no IS NULL OR version_no >= 1)",
            name="ck_portion_standard_approved",
        ),
        sa.CheckConstraint(CANCELLED_CHECK, name="ck_portion_standard_cancelled"),
    )
    op.create_index(op.f("ix_portion_standards_campus_id"), "portion_standards", ["campus_id"])
    op.create_index("ix_portion_standards_menu_item", "portion_standards", ["campus_id", "menu_id", "item_id"])

    op.create_table(
        "portion_standard_basis",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("campus_id", sa.Integer(), nullable=False),
        sa.Column("standard_id", sa.Integer(), nullable=False),
        sa.Column("meal_record_id", sa.Integer(), nullable=False),
        sa.Column("quantity_used", sa.Numeric(precision=18, scale=3), nullable=False),
        sa.Column("unit_id", sa.Integer(), nullable=False),
        sa.Column("people_served", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["campus_id"], ["campuses.id"]),
        sa.ForeignKeyConstraint(["standard_id"], ["portion_standards.id"]),
        sa.ForeignKeyConstraint(["meal_record_id"], ["meal_records.id"]),
        sa.ForeignKeyConstraint(["unit_id"], ["units.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("standard_id", "meal_record_id", name="uq_portion_standard_basis"),
        sa.CheckConstraint("quantity_used > 0", name="ck_portion_standard_basis_quantity"),
        sa.CheckConstraint("people_served > 0", name="ck_portion_standard_basis_people"),
    )
    op.create_index(op.f("ix_portion_standard_basis_campus_id"), "portion_standard_basis", ["campus_id"])
    op.create_index(op.f("ix_portion_standard_basis_standard_id"), "portion_standard_basis", ["standard_id"])

    # ---------- 3. meal plans ----------
    op.create_table(
        "meal_plans",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("campus_id", sa.Integer(), nullable=False),
        sa.Column("plan_seq", sa.Integer(), nullable=False),
        sa.Column("plan_number", sa.String(length=20), nullable=False),
        sa.Column("plan_date", sa.Date(), nullable=False),
        sa.Column("meal_session_id", sa.Integer(), nullable=False),
        sa.Column("menu_id", sa.Integer(), nullable=False),
        sa.Column("expected_headcount", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("notes", sa.String(length=500), nullable=True),
        *audit_columns(),
        sa.ForeignKeyConstraint(["campus_id"], ["campuses.id"]),
        sa.ForeignKeyConstraint(["meal_session_id"], ["meal_sessions.id"]),
        sa.ForeignKeyConstraint(["menu_id"], ["menus.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("campus_id", "plan_seq", name="uq_meal_plan_seq"),
        sa.UniqueConstraint("campus_id", "plan_number", name="uq_meal_plan_number"),
        sa.CheckConstraint("status IN ('DRAFT', 'APPROVED', 'CANCELLED')", name="ck_meal_plan_status"),
        sa.CheckConstraint("expected_headcount >= 1", name="ck_meal_plan_headcount"),
        sa.CheckConstraint(
            "(approved_at IS NULL) = (approved_by IS NULL) "
            "AND (status <> 'APPROVED' OR approved_at IS NOT NULL) "
            "AND (status <> 'DRAFT' OR approved_at IS NULL)",
            name="ck_meal_plan_approved",
        ),
        sa.CheckConstraint(CANCELLED_CHECK, name="ck_meal_plan_cancelled"),
    )
    op.create_index(op.f("ix_meal_plans_campus_id"), "meal_plans", ["campus_id"])
    op.create_index("ix_meal_plans_campus_date", "meal_plans", ["campus_id", "plan_date"])
    op.create_index("uq_meal_plan_session_date", "meal_plans", ["campus_id", "plan_date", "meal_session_id"],
                    unique=True, postgresql_where=sa.text("status <> 'CANCELLED'"))

    op.create_table(
        "meal_plan_lines",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("campus_id", sa.Integer(), nullable=False),
        sa.Column("plan_id", sa.Integer(), nullable=False),
        sa.Column("item_id", sa.Integer(), nullable=False),
        sa.Column("override_quantity_per_person", sa.Numeric(precision=18, scale=3), nullable=True),
        sa.Column("override_unit_id", sa.Integer(), nullable=True),
        sa.Column("override_reason", sa.String(length=500), nullable=True),
        sa.Column("standard_id", sa.Integer(), nullable=True),
        sa.Column("item_kind", sa.String(length=20), nullable=True),
        sa.Column("standard_quantity_per_person", sa.Numeric(precision=18, scale=3), nullable=True),
        sa.Column("standard_unit_id", sa.Integer(), nullable=True),
        sa.Column("quantity_per_person", sa.Numeric(precision=18, scale=3), nullable=True),
        sa.Column("unit_id", sa.Integer(), nullable=True),
        sa.Column("required_quantity", sa.Numeric(precision=18, scale=3), nullable=True),
        sa.Column("rounded_up", sa.Boolean(), nullable=True),
        sa.Column("base_unit_id", sa.Integer(), nullable=True),
        sa.Column("conversion_factor", sa.Numeric(precision=24, scale=12), nullable=True),
        sa.Column("required_base_quantity", sa.Numeric(precision=18, scale=3), nullable=True),
        sa.ForeignKeyConstraint(["campus_id"], ["campuses.id"]),
        sa.ForeignKeyConstraint(["plan_id"], ["meal_plans.id"]),
        sa.ForeignKeyConstraint(["item_id"], ["items.id"]),
        sa.ForeignKeyConstraint(["override_unit_id"], ["units.id"]),
        sa.ForeignKeyConstraint(["standard_id"], ["portion_standards.id"]),
        sa.ForeignKeyConstraint(["standard_unit_id"], ["units.id"]),
        sa.ForeignKeyConstraint(["unit_id"], ["units.id"]),
        sa.ForeignKeyConstraint(["base_unit_id"], ["units.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("plan_id", "item_id", name="uq_meal_plan_line_item"),
        sa.CheckConstraint(
            "(override_quantity_per_person IS NULL) = (override_unit_id IS NULL) "
            "AND (override_quantity_per_person IS NULL) = (override_reason IS NULL) "
            "AND (override_quantity_per_person IS NULL OR override_quantity_per_person > 0) "
            "AND (override_reason IS NULL OR length(trim(override_reason)) > 0)",
            name="ck_meal_plan_line_override",
        ),
        sa.CheckConstraint(
            " AND ".join(f"({c} IS NULL) = (standard_id IS NULL)" for c in SNAPSHOT_COLUMNS[1:]),
            name="ck_meal_plan_line_snapshot",
        ),
        sa.CheckConstraint(
            "required_quantity IS NULL OR (required_quantity > 0 AND required_base_quantity > 0 "
            "AND quantity_per_person > 0 AND standard_quantity_per_person > 0 AND conversion_factor > 0 "
            "AND item_kind IN ('RAW', 'PREPARED'))",
            name="ck_meal_plan_line_values",
        ),
    )
    op.create_index(op.f("ix_meal_plan_lines_campus_id"), "meal_plan_lines", ["campus_id"])
    op.create_index(op.f("ix_meal_plan_lines_plan_id"), "meal_plan_lines", ["plan_id"])

    # ---------- 4. immutability triggers (S6-2) ----------
    for statement in GUARDS:
        op.execute(statement)

    # ---------- 5. permission rows (6-3); no grants ----------
    bind = op.get_bind()
    for code, name in MODULES:
        module_id = bind.execute(
            sa.text("INSERT INTO modules (name, code) VALUES (:name, :code) RETURNING id"),
            {"name": name, "code": code},
        ).scalar_one()
        for action in ACTIONS:
            bind.execute(
                sa.text("INSERT INTO permissions (module_id, action, permission_code) VALUES (:module_id, :action, :code)"),
                {"module_id": module_id, "action": action, "code": f"{code}.{action.lower()}"},
            )


def downgrade() -> None:
    bind = op.get_bind()
    plans = bind.execute(sa.text("SELECT count(*) FROM meal_plans")).scalar_one()
    standards = bind.execute(sa.text("SELECT count(*) FROM portion_standards")).scalar_one()
    classified = bind.execute(sa.text("SELECT count(*) FROM items WHERE item_kind IS NOT NULL")).scalar_one()
    grants = bind.execute(sa.text(
        """
        SELECT count(*) FROM staff_access_assignments a
          JOIN permissions p ON p.id = a.permission_id
          JOIN modules m ON m.id = p.module_id
         WHERE m.code IN ('portion_standard', 'meal_plan')
        """
    )).scalar_one()
    if plans or standards or classified or grants:
        raise RuntimeError(
            f"Planning data exists ({plans} meal plans, {standards} portion standards, {classified} classified items, "
            f"{grants} planning grants); downgrading would lose it. Restore the pre-migration backup instead."
        )
    for code, _name in MODULES:
        bind.execute(sa.text("DELETE FROM permissions WHERE module_id IN (SELECT id FROM modules WHERE code = :code)"),
                     {"code": code})
        bind.execute(sa.text("DELETE FROM modules WHERE code = :code"), {"code": code})

    for trigger, table, function in TRIGGERS:
        op.execute(f"DROP TRIGGER IF EXISTS {trigger} ON {table}")
        op.execute(f"DROP FUNCTION IF EXISTS {function}()")

    op.drop_index(op.f("ix_meal_plan_lines_plan_id"), table_name="meal_plan_lines")
    op.drop_index(op.f("ix_meal_plan_lines_campus_id"), table_name="meal_plan_lines")
    op.drop_table("meal_plan_lines")
    op.drop_index("uq_meal_plan_session_date", table_name="meal_plans")
    op.drop_index("ix_meal_plans_campus_date", table_name="meal_plans")
    op.drop_index(op.f("ix_meal_plans_campus_id"), table_name="meal_plans")
    op.drop_table("meal_plans")
    op.drop_index(op.f("ix_portion_standard_basis_standard_id"), table_name="portion_standard_basis")
    op.drop_index(op.f("ix_portion_standard_basis_campus_id"), table_name="portion_standard_basis")
    op.drop_table("portion_standard_basis")
    op.drop_index("ix_portion_standards_menu_item", table_name="portion_standards")
    op.drop_index(op.f("ix_portion_standards_campus_id"), table_name="portion_standards")
    op.drop_table("portion_standards")

    op.drop_constraint("ck_item_kind", "items", type_="check")
    op.drop_column("items", "item_kind")

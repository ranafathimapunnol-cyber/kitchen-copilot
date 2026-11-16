"""
Static safety checks for the Alembic revision graph.

These tests only read the files in migrations/versions. They never
connect to a database and never run a migration.

They protect against:
* two developers creating parallel migrations (two heads),
* a migration pointing at a parent that does not exist,
* branches or merge revisions appearing without a deliberate decision,
* existing, already-applied migrations being removed or re-ordered.
"""

from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory


API_DIR = Path(__file__).resolve().parents[1]

# Revisions that are already applied to existing databases.
# Their order must never change and none of them may be removed.
APPLIED_HISTORY = [
    "1f304c2445e6",  # initial campus and master data schema
    "77ba3369ea6b",  # add unit dimension
    "fb84dd6fb038",  # add purchase and inventory tables
    "8a2c4d91e6b7",  # add daily headcounts
    "c91f7a2b4e60",  # add three role authorization
    "d4e8a91b2c70",  # add waste tracking module and tables
]


def load_script_directory():
    config = Config(str(API_DIR / "alembic.ini"))
    config.set_main_option(
        "script_location", str(API_DIR / "migrations")
    )
    return ScriptDirectory.from_config(config)


def all_revisions():
    return list(load_script_directory().walk_revisions())


def test_exactly_one_head():
    heads = load_script_directory().get_heads()

    assert len(heads) == 1, (
        f"Expected one migration head, found {heads}. "
        "Re-point the newer migration's down_revision instead of "
        "creating parallel heads."
    )


def test_exactly_one_base():
    bases = load_script_directory().get_bases()

    assert bases == [APPLIED_HISTORY[0]]


def test_every_parent_revision_exists():
    revisions = all_revisions()
    known = {revision.revision for revision in revisions}

    for revision in revisions:
        parents = revision.down_revision

        if parents is None:
            continue

        if isinstance(parents, str):
            parents = (parents,)

        for parent in parents:
            assert parent in known, (
                f"{revision.revision} points to missing parent {parent}"
            )


def test_history_is_linear():
    revisions = all_revisions()

    merges = [
        revision.revision
        for revision in revisions
        if isinstance(revision.down_revision, (tuple, list))
    ]
    assert merges == [], f"Unexpected merge revisions: {merges}"

    children = {}
    for revision in revisions:
        if revision.down_revision:
            children.setdefault(revision.down_revision, []).append(
                revision.revision
            )

    branch_points = {
        parent: kids for parent, kids in children.items() if len(kids) > 1
    }
    assert branch_points == {}, f"Unexpected branches: {branch_points}"


def test_applied_history_is_intact_and_in_order():
    ordered = [
        revision.revision
        for revision in reversed(all_revisions())
    ]

    assert ordered[: len(APPLIED_HISTORY)] == APPLIED_HISTORY


def test_one_file_per_revision():
    versions_dir = API_DIR / "migrations" / "versions"
    files = [
        path for path in versions_dir.glob("*.py")
        if not path.name.startswith("__")
    ]

    assert len(files) == len(all_revisions())

"""Migration 0024 is additive: two new tables, nothing existing is altered, models agree.

This is the structural half of the "dmind never touches existing data" guarantee. The
behavioral half (no writes to tasks, chat, mail...) lives in tests/test_dmind_diagrams.py.
"""

import tempfile
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, inspect, text

ROOT = Path(__file__).resolve().parents[1]
BEFORE = "0023_slack_workspace"
DIAGRAM_TABLES = {"diagrams", "diagram_revisions"}


def config():
    cfg = Config(str(ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(ROOT / "alembic"))
    return cfg


def snapshot(engine):
    """Everything about every table's shape, so any alteration is visible."""
    insp = inspect(engine)
    shape = {}
    for table in insp.get_table_names():
        shape[table] = {
            "columns": sorted(
                (c["name"], str(c["type"]), c["nullable"]) for c in insp.get_columns(table)
            ),
            "pk": sorted(insp.get_pk_constraint(table)["constrained_columns"]),
            "fks": sorted(
                (tuple(f["constrained_columns"]), f["referred_table"], tuple(f["referred_columns"]))
                for f in insp.get_foreign_keys(table)
            ),
            "indexes": sorted(
                (i["name"], tuple(i["column_names"]), bool(i["unique"]))
                for i in insp.get_indexes(table)
            ),
        }
    return shape


@pytest.fixture()
def database(monkeypatch):
    url = f"sqlite:///{Path(tempfile.mkdtemp(prefix='dp-dmind-mig-')) / 'dmind.db'}"
    monkeypatch.setenv("DATABASE_URL", url)
    engine = create_engine(url)
    yield engine
    engine.dispose()


def test_there_is_a_single_migration_head_that_includes_dmind():
    script = ScriptDirectory.from_config(config())
    heads = script.get_heads()
    assert len(heads) == 1
    chain = [rev.revision for rev in script.walk_revisions()]
    assert "0024_dmind_diagrams" in chain
    assert script.get_revision("0024_dmind_diagrams").down_revision == BEFORE


def test_upgrade_adds_only_the_two_dmind_tables_and_alters_nothing_else(database):
    command.upgrade(config(), BEFORE)
    before = snapshot(database)
    assert not DIAGRAM_TABLES & set(before)

    command.upgrade(config(), "0024_dmind_diagrams")
    after = snapshot(database)

    assert set(after) - set(before) == DIAGRAM_TABLES
    assert set(before) <= set(after)  # no table disappeared
    for table, shape in before.items():
        assert after[table] == shape, f"existing table {table} was altered"


def test_downgrade_returns_to_the_previous_schema_and_upgrade_is_repeatable(database):
    command.upgrade(config(), BEFORE)
    before = snapshot(database)
    command.upgrade(config(), "0024_dmind_diagrams")
    command.downgrade(config(), BEFORE)
    assert snapshot(database) == before
    command.upgrade(config(), "head")
    assert DIAGRAM_TABLES <= set(snapshot(database))


def test_migration_matches_the_orm_models(database):
    from daypilot_knowledge.db.base import Base
    from daypilot_knowledge.db import models  # noqa: F401  (registers the tables)

    command.upgrade(config(), "head")
    insp = inspect(database)
    for name in DIAGRAM_TABLES:
        table = Base.metadata.tables[name]
        migrated = {c["name"]: c for c in insp.get_columns(name)}
        assert set(migrated) == {c.name for c in table.columns}, name
        for column in table.columns:
            assert migrated[column.name]["nullable"] == column.nullable, (name, column.name)
        assert sorted(insp.get_pk_constraint(name)["constrained_columns"]) == sorted(
            c.name for c in table.primary_key.columns
        )
    fk = insp.get_foreign_keys("diagram_revisions")
    assert [(f["referred_table"], f["referred_columns"]) for f in fk] == [("diagrams", ["id"])]
    assert ("ix_diagrams_workspace_id", ("workspace_id",), False) in {
        (i["name"], tuple(i["column_names"]), bool(i["unique"])) for i in insp.get_indexes("diagrams")
    }


def test_existing_rows_survive_the_upgrade(database):
    """A real row in an existing table is untouched by the dmind migration."""
    command.upgrade(config(), BEFORE)
    with database.begin() as conn:
        tables = inspect(conn).get_table_names()
        assert "workspaces" in tables
        conn.execute(
            text(
                "INSERT INTO workspaces (id, name, mode, created_by, created_at, updated_at) "
                "VALUES ('keep-me', 'Existing', 'local', 'someone', "
                "CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
            )
        )
    command.upgrade(config(), "0024_dmind_diagrams")
    with database.connect() as conn:
        rows = conn.execute(text("SELECT id, name FROM workspaces")).all()
    assert ("keep-me", "Existing") in [tuple(r) for r in rows]


def test_0025_adds_only_nullable_columns_to_diagrams_and_keeps_rows(database):
    command.upgrade(config(), "0024_dmind_diagrams")
    before = snapshot(database)
    with database.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO diagrams (id, workspace_id, title, revision, archived, document_json) "
                "VALUES ('keep', 'ws', 'Existing', 1, 0, '{}')"
            )
        )
    command.upgrade(config(), "0025_dmind_workspace")
    after = snapshot(database)
    assert set(after) == set(before)
    for table, shape in before.items():
        if table != "diagrams":
            assert after[table] == shape, f"{table} changed"
    added = set(after["diagrams"]["columns"]) - set(before["diagrams"]["columns"])
    assert {c[0] for c in added} == {"project_id", "tags_text"}
    assert all(c[2] for c in added), "new columns must be nullable"
    assert set(before["diagrams"]["columns"]) <= set(after["diagrams"]["columns"])
    with database.connect() as conn:
        row = conn.execute(text("SELECT title, project_id, tags_text FROM diagrams WHERE id='keep'")).one()
    assert tuple(row) == ("Existing", None, None)
    command.downgrade(config(), "0024_dmind_diagrams")
    assert snapshot(database) == before


def test_0026_adds_only_the_shares_table_and_reverses_cleanly(database):
    command.upgrade(config(), "0025_dmind_workspace")
    before = snapshot(database)
    command.upgrade(config(), "0026_dmind_shares")
    after = snapshot(database)
    assert set(after) - set(before) == {"diagram_shares"}
    for table, shape in before.items():
        assert after[table] == shape, f"{table} changed"
    command.downgrade(config(), "0025_dmind_workspace")
    assert snapshot(database) == before


def test_0027_adds_only_the_credit_tables_and_reverses_cleanly(database):
    command.upgrade(config(), "0026_dmind_shares")
    before = snapshot(database)
    command.upgrade(config(), "0027_ai_credits")
    after = snapshot(database)
    assert set(after) - set(before) == {"ai_credit_accounts", "ai_credit_events"}
    for table, shape in before.items():
        assert after[table] == shape, f"{table} changed"
    command.downgrade(config(), "0026_dmind_shares")
    assert snapshot(database) == before

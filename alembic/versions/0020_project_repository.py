"""The repository a project's work lands in.

Additive: ``projects.repository`` makes the repo a first-class property of the
project instead of an untyped entry in ``linked_sources``. A coding run then
inherits it, so "the repo I work on" is answered once per project rather than
retyped for every run. Existing rows are backfilled from the linked source that
already recorded it.

Revision ID: 0020_project_repository
Revises: 0019_profile_observations
Create Date: 2026-08-01
"""
from __future__ import annotations

import json

import sqlalchemy as sa
from alembic import op

revision = "0020_project_repository"
down_revision = "0019_profile_observations"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "projects",
        sa.Column("repository", sa.String(length=500), nullable=False, server_default=""),
    )

    # Backfill from linked_sources: projects created with a repository already
    # recorded it there, so nobody has to re-enter it after upgrading.
    connection = op.get_bind()
    rows = connection.execute(
        sa.text("SELECT id, linked_sources FROM projects")
    ).fetchall()
    for project_id, linked_sources in rows:
        repository = _repository_from(linked_sources)
        if repository:
            connection.execute(
                sa.text("UPDATE projects SET repository = :repo WHERE id = :id"),
                {"repo": repository[:500], "id": project_id},
            )


def _repository_from(linked_sources) -> str:
    if isinstance(linked_sources, str):
        try:
            linked_sources = json.loads(linked_sources)
        except (TypeError, ValueError):
            return ""
    for source in linked_sources or []:
        if isinstance(source, dict) and source.get("kind") == "repository":
            return str(source.get("ref") or "")
    return ""


def downgrade() -> None:
    op.drop_column("projects", "repository")

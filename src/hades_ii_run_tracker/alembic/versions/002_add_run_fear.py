"""Add optional fear column to runs.

Revision ID: 002_add_run_fear
Revises: 001_baseline_schema
Create Date: 2026-02-04

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

revision: str = "002_add_run_fear"
down_revision: Union[str, None] = "001_baseline_schema"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    insp = inspect(bind)
    if not insp.has_table("runs"):
        return
    cols = {c["name"] for c in insp.get_columns("runs")}
    if "fear" in cols:
        return
    with op.batch_alter_table("runs", schema=None) as batch_op:
        batch_op.add_column(sa.Column("fear", sa.Integer(), nullable=True))


def downgrade() -> None:
    bind = op.get_bind()
    insp = inspect(bind)
    if not insp.has_table("runs"):
        return
    cols = {c["name"] for c in insp.get_columns("runs")}
    if "fear" not in cols:
        return
    with op.batch_alter_table("runs", schema=None) as batch_op:
        batch_op.drop_column("fear")

"""Add weighted_victory_fear_multiplier to app_settings.

Revision ID: 004_weighted_victory_multiplier
Revises: 003_fear_option_and_run_default
Create Date: 2026-05-05

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

revision: str = "004_weighted_victory_multiplier"
down_revision: Union[str, None] = "003_fear_option_and_run_default"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    insp = inspect(bind)
    if not insp.has_table("app_settings"):
        return
    cols = {c["name"] for c in insp.get_columns("app_settings")}
    if "weighted_victory_fear_multiplier" in cols:
        return
    with op.batch_alter_table("app_settings", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column(
                "weighted_victory_fear_multiplier",
                sa.Float(),
                nullable=False,
                server_default="0",
            )
        )


def downgrade() -> None:
    bind = op.get_bind()
    insp = inspect(bind)
    if not insp.has_table("app_settings"):
        return
    cols = {c["name"] for c in insp.get_columns("app_settings")}
    if "weighted_victory_fear_multiplier" not in cols:
        return
    with op.batch_alter_table("app_settings", schema=None) as batch_op:
        batch_op.drop_column("weighted_victory_fear_multiplier")

"""Seed Fear option row and default runs.fear to 0.

Revision ID: 003_fear_option_and_run_default
Revises: 002_add_run_fear
Create Date: 2026-05-05

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

revision: str = "003_fear_option_and_run_default"
down_revision: Union[str, None] = "002_add_run_fear"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

def upgrade() -> None:
    bind = op.get_bind()
    insp = inspect(bind)
    if not insp.has_table("runs"):
        return

    cols = {c["name"] for c in insp.get_columns("runs")}
    if "fear" in cols:
        op.execute(sa.text("UPDATE runs SET fear = 0 WHERE fear IS NULL"))
        with op.batch_alter_table("runs", schema=None) as batch_op:
            batch_op.alter_column(
                "fear",
                existing_type=sa.Integer(),
                nullable=False,
                server_default=sa.text("0"),
            )

    if insp.has_table("options"):
        op.execute(
            """
            INSERT INTO options (kind, position, name, image_url, source_url)
            SELECT 'fear', 0, 'Fear', '/static/assets/fear/shrine-point.png',
                'https://hades.fandom.com/wiki/Fear?file=ShrinePoint.png'
            WHERE NOT EXISTS (SELECT 1 FROM options WHERE kind = 'fear')
            """
        )


def downgrade() -> None:
    bind = op.get_bind()
    insp = inspect(bind)
    if insp.has_table("options"):
        op.execute(sa.text("DELETE FROM options WHERE kind = 'fear'"))

    if not insp.has_table("runs"):
        return
    cols = {c["name"] for c in insp.get_columns("runs")}
    if "fear" not in cols:
        return
    with op.batch_alter_table("runs", schema=None) as batch_op:
        batch_op.alter_column(
            "fear",
            existing_type=sa.Integer(),
            nullable=True,
            server_default=None,
        )

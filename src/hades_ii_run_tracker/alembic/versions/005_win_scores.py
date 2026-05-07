"""Win scores and scoring weights; drop weighted_victory_fear_multiplier.

Revision ID: 005_win_scores
Revises: 004_weighted_victory_multiplier
Create Date: 2026-05-07

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect, text

revision: str = "005_win_scores"
down_revision: Union[str, None] = "004_weighted_victory_multiplier"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    insp = inspect(bind)
    if not insp.has_table("app_settings"):
        return

    app_cols = {c["name"] for c in insp.get_columns("app_settings")}
    with op.batch_alter_table("app_settings", schema=None) as batch_op:
        if "fear_weight" not in app_cols:
            batch_op.add_column(
                sa.Column(
                    "fear_weight",
                    sa.Float(),
                    nullable=False,
                    server_default="1",
                )
            )
        if "run_amount_topside" not in app_cols:
            batch_op.add_column(
                sa.Column(
                    "run_amount_topside",
                    sa.Float(),
                    nullable=False,
                    server_default="1.3",
                )
            )
        if "run_amount_bottomside" not in app_cols:
            batch_op.add_column(
                sa.Column(
                    "run_amount_bottomside",
                    sa.Float(),
                    nullable=False,
                    server_default="1",
                )
            )

    insp = inspect(bind)
    run_cols = (
        {c["name"] for c in insp.get_columns("runs")}
        if insp.has_table("runs")
        else set()
    )
    if insp.has_table("runs") and "computed_win_score" not in run_cols:
        with op.batch_alter_table("runs", schema=None) as batch_op:
            batch_op.add_column(sa.Column("computed_win_score", sa.Float(), nullable=True))

        bind.execute(
            text(
                """
                UPDATE runs AS r
                SET computed_win_score = (
                    SELECT
                        (CASE WHEN r.side = 'topside' THEN s.run_amount_topside
                              ELSE s.run_amount_bottomside END)
                        * (1.0 + (
                            MIN(COALESCE(r.fear, 0), 67) / 67.0
                        ) * s.fear_weight)
                    FROM app_settings AS s
                    WHERE s.id = 1
                )
                """
            )
        )

        with op.batch_alter_table("runs", schema=None) as batch_op:
            batch_op.alter_column(
                "computed_win_score",
                existing_type=sa.Float(),
                nullable=False,
                server_default=None,
            )

    app_cols_after = {c["name"] for c in inspect(bind).get_columns("app_settings")}
    if "weighted_victory_fear_multiplier" in app_cols_after:
        with op.batch_alter_table("app_settings", schema=None) as batch_op:
            batch_op.drop_column("weighted_victory_fear_multiplier")


def downgrade() -> None:
    bind = op.get_bind()
    insp = inspect(bind)
    if not insp.has_table("app_settings"):
        return

    app_cols = {c["name"] for c in insp.get_columns("app_settings")}
    if "weighted_victory_fear_multiplier" not in app_cols:
        with op.batch_alter_table("app_settings", schema=None) as batch_op:
            batch_op.add_column(
                sa.Column(
                    "weighted_victory_fear_multiplier",
                    sa.Float(),
                    nullable=False,
                    server_default="0",
                )
            )

    if insp.has_table("runs"):
        run_cols = {c["name"] for c in insp.get_columns("runs")}
        if "computed_win_score" in run_cols:
            with op.batch_alter_table("runs", schema=None) as batch_op:
                batch_op.drop_column("computed_win_score")

    app_cols = {c["name"] for c in inspect(bind).get_columns("app_settings")}
    with op.batch_alter_table("app_settings", schema=None) as batch_op:
        if "fear_weight" in app_cols:
            batch_op.drop_column("fear_weight")
        if "run_amount_topside" in app_cols:
            batch_op.drop_column("run_amount_topside")
        if "run_amount_bottomside" in app_cols:
            batch_op.drop_column("run_amount_bottomside")

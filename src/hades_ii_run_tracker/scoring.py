"""Win score formula (stored per run at submission time)."""

from __future__ import annotations

from .models import AnalyticsSettings, RunSide


def compute_win_score(side: RunSide, fear: int, analytics: AnalyticsSettings) -> float:
    """Raw score before ×100 display scaling."""
    fear_amount = max(0, min(67, int(fear)))
    if side == "topside":
        run_amount = float(analytics.run_amount_topside)
    else:
        run_amount = float(analytics.run_amount_bottomside)
    fear_weight = float(analytics.fear_weight)
    return run_amount * (1.0 + (fear_amount / 67.0) * fear_weight)


def display_points(raw_score: float) -> int:
    return int(round(raw_score * 100.0))

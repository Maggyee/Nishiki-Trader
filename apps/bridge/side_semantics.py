from __future__ import annotations


def side_score_conflict_reason(side: str, score: float) -> str | None:
    """Return a rejection reason when ``side`` and ``score`` disagree."""
    if side == "flat":
        if score != 0.0:
            return f"flat side requires score=0.0, got score={score}"
        return None
    if side == "buy" and score < 0.0:
        return f"buy side requires score>=0.0, got score={score}"
    if side == "sell" and score > 0.0:
        return f"sell side requires score<=0.0, got score={score}"
    return None

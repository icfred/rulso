"""Floating-label recomputation.

M1 stub: returns all labels unassigned. Real implementation defers to M2 once
labels gain dependent rules / dormant-persistent-rule activation.
"""

from __future__ import annotations

from .state import GameState

LABELS: tuple[str, ...] = (
    "THE LEADER",
    "THE WOUNDED",
    "THE GENEROUS",
    "THE CURSED",
)


def recompute(state: GameState) -> dict[str, int | None]:
    """Return seat assignments per label. M1: all unassigned."""
    del state
    return {label: None for label in LABELS}

"""Seeded determinism invariant (RUL-54).

The 12-card effect deck recycles around round ~13. Before RUL-54 the CLI
silently fell through to ``random.Random()`` (unseeded) at that point, so
identical seeds diverged once the recycle path fired. This test pins the
invariant: two back-to-back ``run_game`` invocations on the same seed with
``max_rounds`` past the first recycle MUST produce byte-identical stdout.

Stdout is a strict proxy for ``GameState`` evolution — every per-round event
(``round_start`` effect_card, ``turn`` plays, ``resolve`` rendered, standings)
is derived from state at that point. Byte-equal logs ⇒ byte-equal state.
"""

from __future__ import annotations

import contextlib
import io

import pytest

from rulso.cli import main

_ROUNDS = 50  # well past the 12-card effect deck's first recycle (~round 13)
_SEEDS: tuple[int, ...] = (0, 1, 2)


@pytest.mark.parametrize("seed", _SEEDS)
def test_run_game_is_deterministic_past_effect_deck_recycle(seed: int) -> None:
    runs: list[str] = []
    for _ in range(2):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            main(["--seed", str(seed), "--rounds", str(_ROUNDS)])
        runs.append(buf.getvalue())
    assert runs[0] == runs[1], f"seed={seed}: stdout diverged between runs"


def test_recycle_path_is_actually_exercised() -> None:
    """Guard against the determinism test silently passing if recycle never fires.

    The 12-card effect deck must exhaust at least once within ``_ROUNDS`` for
    the invariant above to be meaningful. We detect exhaustion by counting
    distinct ``effect_card=`` values across the run: with 12 unique cards plus
    ``none``, seeing the deck cycle implies the recycle code path executed.
    """
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        main(["--seed", "0", "--rounds", str(_ROUNDS)])
    text = buf.getvalue()
    # Count rounds that actually started a build (i.e. drew an effect card).
    round_starts = text.count("event=round_start ")
    # If more rounds were started than the 12-card deck holds, recycle had to
    # have fired at least once. (Failed dealer-seed rounds also count and they
    # too discard the unused effect card, so the threshold is conservative.)
    assert round_starts > 12, f"only {round_starts} rounds started; cannot verify recycle was hit"

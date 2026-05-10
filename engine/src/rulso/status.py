"""Status-token primitives — apply / clear / decay (RUL-40, follows RUL-30).

5 status tokens per ``design/state.md`` ``PlayerStatus``:

* ``burn`` — counter; multiple BURN tokens stack. Drains ``BURN_TICK`` chips
  per token at ``round_start`` step 2. Cleared by ``CLEAR_BURN`` cards.
* ``mute`` — toggle. Blocks MODIFIER plays for the round following
  application. Clears at ``round_start`` step 2 (one-round lifetime).
* ``blessed`` — toggle. Cancels the next chip-loss the bearer suffers
  (including the BURN tick at ``round_start`` step 2; RUL-49); clears on
  use via :func:`consume_blessed_or_else`.
* ``marked`` — toggle. Used by ``EACH PLAYER`` rule scoping; clears at
  ``resolve`` step 10 (one-round lifetime).
* ``chained`` — toggle. Blocks goal-claim eligibility. Clears via
  ``CLEAR_CHAINED`` cards only (no natural decay).

Toggles are non-stackable: re-application while held is a no-op (does not
refresh, does not stack). Only ``burn`` is countable.

Three call sites consume this module:

* ``rules.enter_round_start`` step 2 → :func:`tick_round_start`
  (BURN tick + MUTE clear; replaces M1.5 ``rules._apply_burn_tick``).
* ``rules.enter_resolve`` step 10 → :func:`tick_resolve_end`
  (MARKED clear; net-new in M2).
* ``effects.dispatch_effect`` (registered handlers) → ``apply_*`` / ``clear_*``
  primitives via the effect-kind registry. Status-applying / -clearing kinds
  register themselves at module load — importing :mod:`rulso.effects`
  triggers this module (``effects.py`` imports us at the bottom) so the
  registrations fire eagerly without a circular bootstrap.

All functions are pure: input ``Player`` / ``GameState`` is never mutated.
"""

from __future__ import annotations

from rulso import effects
from rulso.state import BURN_TICK, GameState, Player

# --- Single-player primitives -----------------------------------------------


def apply_burn(player: Player, magnitude: int = 1) -> Player:
    """Add ``magnitude`` BURN tokens to ``player``. Counter — stacks."""
    new_status = player.status.model_copy(update={"burn": player.status.burn + magnitude})
    return player.model_copy(update={"status": new_status})


def apply_mute(player: Player) -> Player:
    """Set MUTE on ``player``. Re-application while held is a no-op."""
    if player.status.mute:
        return player
    new_status = player.status.model_copy(update={"mute": True})
    return player.model_copy(update={"status": new_status})


def apply_blessed(player: Player) -> Player:
    """Set BLESSED on ``player``. Re-application while held is a no-op."""
    if player.status.blessed:
        return player
    new_status = player.status.model_copy(update={"blessed": True})
    return player.model_copy(update={"status": new_status})


def apply_marked(player: Player) -> Player:
    """Set MARKED on ``player``. Re-application while held is a no-op."""
    if player.status.marked:
        return player
    new_status = player.status.model_copy(update={"marked": True})
    return player.model_copy(update={"status": new_status})


def apply_chained(player: Player) -> Player:
    """Set CHAINED on ``player``. Re-application while held is a no-op."""
    if player.status.chained:
        return player
    new_status = player.status.model_copy(update={"chained": True})
    return player.model_copy(update={"status": new_status})


def clear_burn(player: Player) -> Player:
    """Clear all BURN tokens on ``player`` (sets ``burn = 0``).

    M2 starter clears in one shot per ``design/status-tokens.md`` BURN row;
    one-by-one decrement is deferred. No-op when ``burn`` is already 0.
    """
    if player.status.burn == 0:
        return player
    new_status = player.status.model_copy(update={"burn": 0})
    return player.model_copy(update={"status": new_status})


def clear_chained(player: Player) -> Player:
    """Clear CHAINED on ``player``. No-op when not held."""
    if not player.status.chained:
        return player
    new_status = player.status.model_copy(update={"chained": False})
    return player.model_copy(update={"status": new_status})


# --- Decay ticks ------------------------------------------------------------


def tick_round_start(player: Player) -> Player:
    """``round_start`` step 2: drain ``BURN_TICK × burn`` chips and clear MUTE.

    BURN tokens themselves persist (only the chip drain ticks). MUTE flag
    clears per its one-round lifetime regardless of BLESSED.

    BLESSED interaction (RUL-49, ``design/status-tokens.md`` flag 1): when
    BLESSED and BURN are both held, the chip drain is routed through
    :func:`consume_blessed_or_else` — BLESSED clears, BURN tokens persist,
    chips are unchanged. With BURN==0 the tick has nothing to drain, so
    BLESSED is left intact (a zero-loss event must not consume the token).
    """
    burn = player.status.burn
    drain = BURN_TICK * burn
    if drain > 0:
        player = consume_blessed_or_else(player, drain)
    new_status = player.status.model_copy(update={"mute": False})
    return player.model_copy(update={"status": new_status})


def tick_resolve_end(player: Player) -> Player:
    """``resolve`` step 10: clear MARKED tokens (one-round lifetime)."""
    if not player.status.marked:
        return player
    new_status = player.status.model_copy(update={"marked": False})
    return player.model_copy(update={"status": new_status})


def consume_blessed_or_else(player: Player, loss: int) -> Player:
    """If BLESSED, cancel ``loss`` and clear BLESSED; else apply chip loss.

    Single point of integration for every chip-loss site (RUL-49). Live call
    sites: :func:`tick_round_start` (BURN tick) and ``effects._lose_chips``
    (``LOSE_CHIPS`` effect). Callers are responsible for skipping zero-magnitude
    paths so a no-op event does not silently consume a held BLESSED.
    """
    if player.status.blessed:
        new_status = player.status.model_copy(update={"blessed": False})
        return player.model_copy(update={"status": new_status})
    new_chips = max(0, player.chips - loss)
    return player.model_copy(update={"chips": new_chips})


# --- Effect-handler adapters -----------------------------------------------
#
# The dispatcher (``effects.dispatch_effect``) hands each handler
# ``(state, targets, magnitude)``. These adapters fan the matching primitive
# out across every player in ``targets`` and re-emit the new state. Targets
# missed by a primitive (e.g. a non-existent player id) are silently skipped
# — the dispatcher's target_modifier rewrite already filters to live ids.


def _apply_burn_handler(state: GameState, targets: frozenset[str], magnitude: int) -> GameState:
    new_players = tuple(apply_burn(p, magnitude) if p.id in targets else p for p in state.players)
    return state.model_copy(update={"players": new_players})


def _clear_burn_handler(state: GameState, targets: frozenset[str], _magnitude: int) -> GameState:
    new_players = tuple(clear_burn(p) if p.id in targets else p for p in state.players)
    return state.model_copy(update={"players": new_players})


def _apply_mute_handler(state: GameState, targets: frozenset[str], _magnitude: int) -> GameState:
    new_players = tuple(apply_mute(p) if p.id in targets else p for p in state.players)
    return state.model_copy(update={"players": new_players})


def _apply_blessed_handler(state: GameState, targets: frozenset[str], _magnitude: int) -> GameState:
    new_players = tuple(apply_blessed(p) if p.id in targets else p for p in state.players)
    return state.model_copy(update={"players": new_players})


def _apply_marked_handler(state: GameState, targets: frozenset[str], _magnitude: int) -> GameState:
    new_players = tuple(apply_marked(p) if p.id in targets else p for p in state.players)
    return state.model_copy(update={"players": new_players})


def _apply_chained_handler(state: GameState, targets: frozenset[str], _magnitude: int) -> GameState:
    new_players = tuple(apply_chained(p) if p.id in targets else p for p in state.players)
    return state.model_copy(update={"players": new_players})


def _clear_chained_handler(state: GameState, targets: frozenset[str], _magnitude: int) -> GameState:
    new_players = tuple(clear_chained(p) if p.id in targets else p for p in state.players)
    return state.model_copy(update={"players": new_players})


# Module-load registrations — covers the 7-card M2 starter subset
# (``design/status-tokens.md`` "M2 starter subset" table). Last-write-wins
# per ``effects.register_effect_kind`` contract; importing this module
# multiple times is idempotent.
effects.register_effect_kind("APPLY_BURN", _apply_burn_handler)
effects.register_effect_kind("CLEAR_BURN", _clear_burn_handler)
effects.register_effect_kind("APPLY_MUTE", _apply_mute_handler)
effects.register_effect_kind("APPLY_BLESSED", _apply_blessed_handler)
effects.register_effect_kind("APPLY_MARKED", _apply_marked_handler)
effects.register_effect_kind("APPLY_CHAINED", _apply_chained_handler)
effects.register_effect_kind("CLEAR_CHAINED", _clear_chained_handler)

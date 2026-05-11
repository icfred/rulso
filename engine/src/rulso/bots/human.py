"""Human-driven action selector — TTY counterpart to ``bots.random``.

Shares the engine's action shapes (``PlayCard``, ``PlayJoker``,
``DiscardRedraw``, ``Pass``) and legal-action enumeration with the random
bot via :mod:`rulso.legality`, so the human's menu is identical to what the
bot would consider. Pure I/O wiring; the engine's pure functions stay
untouched.

stdin / stdout are injected so the CLI can pipe scripted input in tests
without monkey-patching ``sys.stdin``. EOF on stdin is treated as a forced
``Pass`` so a stalled or piped game still terminates cleanly.
"""

from __future__ import annotations

from typing import TextIO

from rulso.legality import (
    Action,
    DiscardRedraw,
    Pass,
    PlayCard,
    PlayJoker,
    enumerate_legal_actions,
)
from rulso.state import GameState, Player


def select_action(
    state: GameState,
    player: Player,
    *,
    stdin: TextIO,
    stdout: TextIO,
) -> Action:
    """Prompt the human at ``player`` for one action; return the chosen Action.

    Reads single-line index choices from ``stdin``; loops on invalid input
    (non-integer / out-of-range) without crashing. Returns ``Pass`` when the
    legal-action list is empty or stdin reaches EOF.
    """
    actions = enumerate_legal_actions(state, player)
    _render_prompt(state, player, actions, stdout)
    if not actions:
        return Pass()
    while True:
        line = stdin.readline()
        if not line:
            stdout.write("event=human_input outcome=eof_pass\n")
            return Pass()
        choice = line.strip()
        try:
            idx = int(choice)
        except ValueError:
            stdout.write(
                f"event=human_input outcome=invalid value={choice!r} max={len(actions) - 1}\n"
            )
            continue
        if 0 <= idx < len(actions):
            return actions[idx]
        stdout.write(f"event=human_input outcome=out_of_range value={idx} max={len(actions) - 1}\n")


def _render_prompt(
    state: GameState,
    player: Player,
    actions: list[PlayCard | PlayJoker | DiscardRedraw],
    stdout: TextIO,
) -> None:
    """Emit the human-readable per-turn prompt header, hand, rule, and menu."""
    s = player.status
    stdout.write(
        f"event=human_prompt round={state.round_number} seat={player.seat} "
        f"player={player.id} chips={player.chips} vp={player.vp} "
        f"hand_size={len(player.hand)} actions={len(actions)}\n"
    )
    for i, card in enumerate(player.hand):
        stdout.write(f"  hand[{i}] id={card.id} type={card.type.value} name={card.name}\n")
    rule = state.active_rule
    if rule is not None:
        stdout.write(f"  rule template={rule.template.value}\n")
        for slot in rule.slots:
            if slot.filled_by is not None:
                mods = (
                    f" modifiers={','.join(m.name for m in slot.modifiers)}"
                    if slot.modifiers
                    else ""
                )
                stdout.write(
                    f"    slot {slot.name}={slot.filled_by.name}({slot.filled_by.id}) "
                    f"type={slot.type.value}{mods}\n"
                )
            else:
                stdout.write(f"    slot {slot.name}=<empty> type={slot.type.value}\n")
        if rule.joker_attached is not None:
            stdout.write(f"    joker={rule.joker_attached.name}\n")
    stdout.write(
        f"  status burn={s.burn} mute={s.mute} blessed={s.blessed} "
        f"marked={s.marked} chained={s.chained}\n"
    )
    if not actions:
        stdout.write("  no legal action — pass forced.\n")
        return
    for i, action in enumerate(actions):
        stdout.write(f"  [{i}] {_describe_action(action)}\n")
    stdout.write("> ")


def _describe_action(action: PlayCard | PlayJoker | DiscardRedraw) -> str:
    if isinstance(action, PlayCard):
        dice = "" if action.dice is None else f" dice={action.dice}"
        return f"play_card card={action.card_id} slot={action.slot}{dice}"
    if isinstance(action, PlayJoker):
        return f"play_joker card={action.card_id}"
    if isinstance(action, DiscardRedraw):
        return f"discard_redraw cards={','.join(action.card_ids)}"
    return repr(action)

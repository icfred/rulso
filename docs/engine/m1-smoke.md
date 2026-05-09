_Last edited: 2026-05-10 by RUL-22_

# M1 smoke tests

Cross-cutting integration tests that prove M1's empty-hand reality holds end
to end. Per-function unit tests live in `test_round_flow.py`, `test_resolver.py`,
`test_random_bot.py`, and `test_cli_smoke.py`; this set composes them.

## Files

| Test | Surface | Asserts |
|---|---|---|
| `engine/tests/test_cli_multiseed.py` | `rulso.cli.run_game` over 20 seeds | every run terminates without exception, exits non-zero (cap-hit), emits `game_start` / `round_start` / `rule_failed` / `cap_hit` events, never emits `game_end` |
| `engine/tests/test_smoke_state_transitions.py` | `rulso.rules` end-to-end | LOBBY → ROUND_START → BUILD → RESOLVE via hand-injected fixture; failed-rule fail-and-rotate; full 4-round dealer rotation; `active_seat = (dealer+1) % PLAYER_COUNT` invariant at every dealer position |
| `engine/tests/test_smoke_resolution_edges.py` | `rulso.effects.resolve_if_rule`, `rulso.rules` fail path | M2-stub label SUBJECT (GENEROUS / CURSED / MARKED / CHAINED) → state-equal no-op; live label firing leaves active goals untouched; failed rule never mutates chips / VP / goals; partial-fill failed rule discards played fragments without firing the resolver. Live-label firing tests (LEADER / WOUNDED) live in `test_resolver.py` after RUL-22. |

## Why every M1 game cap-hits

Hands are empty in M1 (deck and dealing land with `cards.yaml`). The
random-legal bot enumerates legal plays from each player's hand; with no hand
cards, the only legal action is `Pass`. Every build revolution finishes with
slots `noun`, `modifier`, `noun_2` unfilled, so `rules._fail_rule_and_rotate`
fires every round. The CLI then ticks the round counter until `--rounds`
exhausts and exits non-zero. `event=cap_hit` is the M1-correct termination
event, not a bug.

The "real game produces a winner" assertion belongs to RUL-21 (M1.5), not here.

## Slot-name mismatch caveat

`rules.py` M1 stub uses lowercase slot names `subject / noun / modifier /
noun_2`. `grammar.render_if_rule` expects `SUBJECT / QUANT / NOUN`. The
resolver path is therefore exercised in `test_smoke_resolution_edges.py` via a
grammar-compatible `RuleBuilder` constructed directly in the test fixture, not
through `rules.py`. Reconciliation is RUL-18's job.

## Determinism

Every test injects an explicit RNG seed (parametrised over 20 seeds for the
CLI sweep). No global RNG, no time-based seeds, no flakes.

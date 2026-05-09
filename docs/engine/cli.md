_Last edited: 2026-05-09 by RUL-11_

# cli.py — round-by-round CLI runner

`rulso.cli` plays one game with 4 random-legal bots and emits line-oriented
event records to stdout. M1 substrate driver — verifies the round-flow phase
machine and bot integration end-to-end.

## Module: `rulso.cli`

### Public API

| Symbol | Signature | Purpose |
|---|---|---|
| `main(argv=None)` | `Sequence[str] \| None → int` | argparse + run_game; entry point for the `rulso` script |
| `run_game(*, seed, max_rounds, out)` | `(int, int, TextIO) → int` | Drive one full game; emit events to `out` |

### Console script

`pyproject.toml` registers:

```toml
[project.scripts]
rulso = "rulso.cli:main"
```

Run with `uv run --project engine rulso [flags]`.

### Flags

| Flag | Default | Meaning |
|---|---|---|
| `--seed <int>` | `0` | RNG seed passed to `random.Random` for bot decisions |
| `--rounds <int>` | `50` | Round cap; non-zero exit if reached without a winner |

### Exit codes

| Code | Condition |
|---|---|
| `0` | A player reached `VP_TO_WIN`; `event=game_end` emitted |
| `1` | Round cap reached without a winner; `event=cap_hit` emitted |

## Output schema

Every line is `event=<name>` followed by space-separated `key=value` pairs
(snake_case, no quoting, no ANSI). Greppable by event name.

| Event | Fields | When |
|---|---|---|
| `game_start` | `seed`, `max_rounds`, `players` | Once at startup |
| `round_start` | `round`, `dealer`, `template`, `effect_card` | After each `enter_round_start` |
| `rule_template` | `round`, `slots` | After `round_start`, lists slot definitions |
| `dealer_fragment` | `round`, `player`, `slot`, `card` | Dealer's slot-0 fill (one entry per existing play) |
| `turn` | `round`, `seat`, `player`, `action`, [`card`, `slot`, `dice` \| `cards`] | Each build-phase turn |
| `rule_failed` | `round`, `unfilled_slots`, `filled_slots`, `next_dealer` | Build revolution ended with at least one unfilled slot |
| `resolve` | `round`, `status`, `template`, `rendered`, `slots` | Build revolution ended with all slots filled |
| `standings` | `round`, `players` (space-joined `pX=chips:N,vp:N`) | After every fail / resolve / cap-hit / game-end |
| `cap_hit` | `rounds_started`, `winner=none` | Round cap reached |
| `game_end` | `winner`, `winner_seat`, `rounds_started` | A player's `vp >= VP_TO_WIN` |

### `turn.action` values

| Value | Extra fields | Source |
|---|---|---|
| `play_card` | `card`, `slot`, `dice` (`1`/`2`/`none`) | bot returned `PlayCard` |
| `pass` | — | bot returned `Pass` |
| `discard_redraw_unimplemented` | `cards` (comma-joined ids) | bot returned `DiscardRedraw`; rules.py has no discard API yet, so the CLI passes the turn and flags it (unreachable in M1 — empty hands) |

## M1 behaviour notes

- M1 hands are empty (`Player.hand = ()` from `start_game`). Every bot decision is `Pass`.
- Build always ends with only the dealer's pre-filled SUBJECT slot, so the rule fails every round (`event=rule_failed`).
- Dealer rotates on every fail. After 4 rounds the dealer has cycled through all four seats.
- No rule reaches `RESOLVE` in M1 → `event=resolve` never fires; chip / vp totals stay at the start values; cap is always hit.
- The CLI never invokes `grammar.render_if_rule` or `effects.resolve_if_rule` because the M1 stub rule in `rules.py` uses slot names `subject/noun/modifier/noun_2` while the resolver expects `SUBJECT/QUANT/NOUN`. Reconciling that substrate is a follow-up ticket; once the slot names align and hands are populated, `_narrate_resolve` is the wiring point for the resolver call.

## Tests

`engine/tests/test_cli_smoke.py`:

- `test_main_runs_to_cap_without_exceptions`
- `test_run_game_emits_round_start_events`
- `test_main_default_seed_and_rounds_run_succeeds`

Full game-completion semantics (real winners, effect application) are RUL-12.

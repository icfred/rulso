_Last edited: 2026-05-10 by RUL-52_

# cli.py — round-by-round CLI runner

`rulso.cli` plays one game with 4 random-legal bots and emits line-oriented
event records to stdout. M1 substrate driver — verifies the round-flow phase
machine and bot integration end-to-end.

## Module: `rulso.cli`

### Public API

| Symbol | Signature | Purpose |
|---|---|---|
| `main(argv=None)` | `Sequence[str] \| None → int` | argparse + run_game; entry point for the `rulso` script |
| `run_game(*, seed, max_rounds, out, human_seat=None, human_stdin=None)` | `(int, int, TextIO, int\|None, TextIO\|None) → int` | Drive one full game; emit events to `out`. When `human_seat` is set, that seat is driven by `rulso.bots.human.select_action` via `human_stdin`. |

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
| `--human-seat <0..3>` | unset | Drive the named seat from the terminal (`stdin`); other seats stay random bots. Omit for the four-bot baseline. |

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
| `human_prompt` | `round`, `seat`, `player`, `chips`, `vp`, `hand_size`, `actions` | Human-seat turn header. Followed by indented hand / rule / status / numbered menu lines and a `> ` prompt; the latter are not `event=` records. |
| `human_input` | `outcome` (`invalid` / `out_of_range` / `eof_pass`), `value`, `max` | Human-seat input rejection or EOF fallback. Loops until a valid index is read; not emitted for the accepted choice. |

### `turn.action` values

| Value | Extra fields | Source |
|---|---|---|
| `play_card` | `card`, `slot`, `dice` (`1`/`2`/`none`) | bot returned `PlayCard` |
| `pass` | — | bot returned `Pass` |
| `discard_redraw_unimplemented` | `cards` (comma-joined ids) | bot returned `DiscardRedraw`; rules.py has no discard API yet, so the CLI passes the turn and flags it (unreachable in M1 — empty hands) |
| `play_joker` | `card` | bot or human returned `PlayJoker`; dispatched via `rules.play_joker` |

## M1 behaviour notes

- M1 hands are empty (`Player.hand = ()` from `start_game`). Every bot decision is `Pass`.
- Build always ends with only the dealer's pre-filled SUBJECT slot, so the rule fails every round (`event=rule_failed`).
- Dealer rotates on every fail. After 4 rounds the dealer has cycled through all four seats.
- No rule reaches `RESOLVE` in M1 → `event=resolve` never fires; chip / vp totals stay at the start values; cap is always hit.
- The CLI never invokes `grammar.render_if_rule` or `effects.resolve_if_rule` because the M1 stub rule in `rules.py` uses slot names `subject/noun/modifier/noun_2` while the resolver expects `SUBJECT/QUANT/NOUN`. Reconciling that substrate is a follow-up ticket; once the slot names align and hands are populated, `_narrate_resolve` is the wiring point for the resolver call.

## Human-seat driver (RUL-52)

`engine/src/rulso/bots/human.py` — `select_action(state, player, *, stdin, stdout) -> Action`

- Mirrors `bots.random` action shapes (`PlayCard` / `PlayJoker` / `DiscardRedraw` / `Pass`); reuses `bots.random.enumerate_legal_actions` for the menu source so the human's choices match what the bot would consider.
- Reads single-line index choices from `stdin` (1-line per choice). Loops on non-integer or out-of-range input, emitting an `event=human_input` record per rejection — the engine does not crash on bad input.
- EOF on `stdin` is treated as a forced `Pass` (`outcome=eof_pass`), so a piped game with insufficient scripted input still terminates cleanly under the round cap.
- Pure I/O wiring; engine pure functions (`rules.*`, `effects.*`) are not touched. Each turn's `Action` is dispatched by the same `_drive_build_turn` branch the bot uses.

The CLI only routes a turn through this driver when `--human-seat == state.active_seat`; the other three seats stay on the random-legal bot, so the M1.5 baseline (`uv run rulso --seed 0`) is preserved byte-for-byte when the flag is omitted.

## Tests

`engine/tests/test_cli_smoke.py`:

- `test_main_runs_to_cap_without_exceptions`
- `test_run_game_emits_round_start_events`
- `test_main_default_seed_and_rounds_run_succeeds`

`engine/tests/test_cli_human_seat.py` (RUL-52):

- `test_human_seat_picks_first_action_terminates`
- `test_human_seat_rejects_invalid_then_accepts`
- `test_human_seat_eof_falls_back_to_pass`
- `test_no_human_seat_default_emits_no_human_events`
- `test_main_human_seat_flag_parses_and_runs`
- `test_human_seat_each_seat_index_works[0..3]`
- `test_main_rejects_human_seat_out_of_range`

Full game-completion semantics (real winners, effect application) are RUL-12.

_Last edited: 2026-05-13 by RUL-76_

# ISMCTS spike

`engine/src/rulso/bots/ismcts.py` — `choose_action(state, player_id, rng, *, rollouts=DEFAULT_ROLLOUTS, max_rollout_rounds=DEFAULT_MAX_ROLLOUT_ROUNDS) -> Action`

Minimum viable Information Set Monte Carlo Tree Search. Same interface as `bots.random.choose_action`; consumers (sim harness, future engine server) swap the import to drive a smart seat without other plumbing.

## Algorithm

1. Non-BUILD phase → pass-through to `bots.random.choose_action`. The spike's scope is BUILD-phase action selection only; SHOP / dice / ROUND_START decisions inherit the random heuristic.
2. `legality.enumerate_legal_actions(state, player)` — same call the human-seat driver uses.
3. Empty legal set → `Pass()`. Single legal action → return it directly (no rollouts; non-trivial fraction of turns hit this path).
4. For each legal action:
   - Sample one information-set realisation via `_sample_opponent_hands` (uniform shuffle of `state.deck` + every opponent's hand; preserves hand-size shape).
   - Apply the candidate action (`play_card` / `play_joker` / `discard_redraw` / `pass_turn`) against the sampled state.
   - Drive the rest of the game with `bots.random` for every seat. Cap at `max_rollout_rounds`; uncapped rollouts could chase JOKER:ECHO / WHILE loops indefinitely.
   - Score `+1` if `state.winner.id == player_id` else `0`.
5. Repeat step 4 K (`rollouts`) times per action.
6. Pick the action with the highest aggregate win count. Tie-break by lowest enumeration index → deterministic given the input rng.

## Constants

| Name | Value | Notes |
|---|---|---|
| `DEFAULT_ROLLOUTS` | `25` | Halved from the hand-over's 50 per stop-condition (b) — see Speed section. |
| `DEFAULT_MAX_ROLLOUT_ROUNDS` | `200` | Mirrors `simulate._DEFAULT_ROUNDS`. |

## Determinism

`choose_action` derives a per-rollout `random.Random(rng.randint(0, 2**31-1))` so that two invocations of `choose_action` with `random.Random(seed)` produce byte-identical decision paths. Rollouts share their own seeded sub-rng for hand sampling, action application, and random-bot rollout — no module-level state.

## Speed (RUL-76 spike-shipped numbers)

- 2-game smoke at default 25 rollouts: ~70s/game (ISMCTS on seat 0; random on seats 1-3).
- DoD's "100-game sweep <90s" gate is **~80× over budget**. Flagged in the RUL-76 hand-back.
- Dominant cost: each rollout drives a full game from mid-state through `Phase.END`, paying Pydantic `model_copy` + observer wrapping on every `GameState` mutation.
- Per stop-condition (b), the spike ships at 25 rollouts (not 50) and the speed gate is dropped. Rollout-count sweep, shallow eval function, and observer-overhead profiling are the documented next-iteration tickets.

## Operator MODIFIER substrate gap (carried from RUL-43)

ISMCTS inherits the `legality._enumerate_plays` skip on operator MODIFIERs (`BUT` / `AND` / `OR` / `MORE_THAN` / `AT_LEAST`). Until a `play_operator` action shape lands — covering enumeration, a `rules.play_operator` apply path attaching to `Slot.modifiers`, and the protocol-layer additive — operator MODIFIERs remain unplayable. Tested negatively in `test_ismcts.test_operator_modifiers_remain_dead_until_substrate_lands` so the regression flips visibly once the substrate ticket ships.

## Sim harness wiring (`rulso simulate`)

`simulate.py` adds `--bot-a` / `--bot-b` (choices: `random`, `ismcts`). `bot_a` drives seat 0; `bot_b` drives seats 1-3 — the spike's asymmetric eval shape. Defaults are `random` / `random` so existing callers see no behaviour change.

- JSON `config` block gains `bot_a` and `bot_b` string fields.
- Terminal summary adds a `head-to-head:` line whenever `bot_a != bot_b`, e.g. `head-to-head: seat 0 (ismcts) wins 12/20 (60.0%) vs seats 1-3 (random) wins 8/20`.
- Observer wrapping is paused around every `bot.choose_action` / `bot.select_purchase` call via `_Observer.pause_depth` — without the pause, ISMCTS rollouts inflate every effect/status counter by ~1000× (each candidate action runs many engine paths the canonical-game observers should not see).

## Out of scope (iteration tickets)

- Eval-function tuning (vp_delta + chip + status weights; replaces raw win-rate).
- Information-set sampling sophistication (currently uniform; later: weight by past plays, score equivocation).
- Tree reuse across turns (currently rebuilt per choice).
- Rollout count / depth sweep (5 / 10 / 25 / 50 / 100 / 200).
- Performance optimisation (Pydantic copy hot path, shallow rollouts).
- JOKER / SHOP / dice heuristics.
- `play_operator` substrate (RUL-43 follow-up).

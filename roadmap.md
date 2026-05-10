# Rulso — Roadmap

Five milestones from empty repo to playable MVP. Each milestone is a vertical slice — engine, content, and tests — not a phase of horizontal work.

## M1: Engine core

**Goal**: A 4-player game runs end-to-end via CLI with random bots. IF rules resolve. State machine is sound.

Definition of done:
- `engine/` repo bootstrapped with `uv`, pydantic v2, websockets, pytest
- `GameState`, `Player`, `Card`, `RuleBuilder` modeled in pydantic
- Round flow phases (`round_start`, `build`, `resolve`) transition correctly
- One IF rule shape (`IF [SUBJECT] HAS [QUANT] [NOUN]`) parses, resolves, applies effect
- 4 random-legal bots play a full game to `VP_TO_WIN` without crashing
- CLI prints round-by-round narration of plays and resolutions
- Smoke tests cover state transitions and rule-resolution edge cases (failed rule, unassigned label)

## M1.5: Watchable engine

**Goal**: bridge between M1 (sound state machine) and M2 (full card set). After M1.5, `uv run rulso --seed 0` produces a CLI game where bots play real cards from real hands, IF rules sometimes resolve, and someone can win.

Definition of done:
- `design/cards-inventory.md` exists (full intended card list with M1.5 starter subset called out)
- `design/cards.yaml` written with ~20 starter cards (1 IF condition + 4–6 SUBJECTs incl. literal seats + LEADER/WOUNDED labels + 2 NOUNs CHIPS/VP + 5 comparator MODs at varied N)
- Hands populated at `start_game(seed)` from a seeded shuffled deck
- `enter_round_start` draws a real CONDITION card; the dealer's first slot is filled from their actual hand
- Labels module computes LEADER and WOUNDED; other labels stay empty for M2
- IF rule effect awards +1 VP (was +1 chip stub in M1)
- Across seeds 0–9, all CLI runs terminate without exception, ≥1 produces a winner, ≥N rules resolve successfully
- README has a "Try it" section pointing at `uv run rulso --seed 0`

Out of scope: WHEN/WHILE rules, JOKERs, GENEROUS/CURSED/MARKED/CHAINED labels, polymorphic rendering, SHOP rounds, dice-driven comparator N, goal cards, effect catalogue beyond the +1 VP stub. All M2.

## M2: Full card set

**Goal**: Every card type and mechanic from `design/cards.yaml` works.

Definition of done:
- `design/cards.yaml` written (separate task, depends on `state.md` only)
- Card schema loaded into engine; slot-compat tags enforced
- Polymorphic rendering working: same card renders differently by neighbor context
- Dice mechanic for comparator MODs (1d6 / 2d6 player choice)
- WHEN rule lifecycle: stored, evaluated on triggers, fires once, discards
- WHILE rule lifecycle: stored, evaluated each round + on triggers
- JOKERs: persistence-conversion working (IF→WHEN at minimum)
- Goal cards: 3 face-up, claim awards VP, replenish from goal deck
- Labels recompute correctly (LEADER, WOUNDED, GENEROUS, CURSED)
- Status tokens (BURN, MUTE, BLESSED, MARKED, CHAINED) apply, decay, and clear per `state.md`
- SHOP round runs every 3 rounds with correct purchase order

## M2.5: Mechanic gaps (pre-M3 sweep)

**Goal**: close M2 mechanics that ship in code but not in play. Tracked as `parent = RUL-24` follow-ups, not a separate Linear milestone.

Definition of done:
- SHOP content lands in `cards.yaml shop_cards:` (RUL-56) — SHOP fires every 3 rounds with non-empty offers
- MARKED is consumed in `EACH_PLAYER` scoping per `design/status-tokens.md` (narrow to MARKED holders when ≥1; otherwise fire normally)
- `cards.yaml effect_cards:` lists `eff.marked.apply` and `eff.chained.clear` so MARKED can be applied and CHAINED can be cleared in production runs
- `bots.md` dice-mode drift fixed (RUL-57)

## M3: Foundation/Minimal Client

**Goal**: a human can sit down, read the board, make a meaningful decision, and reach a winner. Ugly but playable. See `docs/decisions/ADR-0006-foundation-client-before-ismcts.md` for the milestone-reorder rationale.

Definition of done:
- Engine WebSocket protocol (`engine/src/rulso/protocol.py`): Pydantic envelopes for state-broadcast and action-submit
- Engine WebSocket server (`engine/src/rulso/server.py`): asyncio loop, one human seat per connection, bots fill the rest
- TypeScript-from-Pydantic type generation pipeline (`scripts/regenerate-types.sh`)
- `client/` bootstrapped with Vite + Pixi v8 + TypeScript per `tech.md`
- Client connects, parses state, renders: hand with full card text, active rule with semantic preview ("if you complete this rule with GT, it reads `IF p2 GT 2d6 ROUNDS → eff.noop`"), 3 active goal cards with claim conditions visible, all 4 opponents' public state (chips, VP, hand size, status tokens, floating labels), revealed effect for the round
- Input: click-to-play onto a slot, discard via card-toggle (not flat enumeration), JOKER attachment, dice-mode pick where the comparator is OP-only
- Basic dice-roll text/output (no animation)
- `bots.human` rewired through the WebSocket; `bots.random` continues to fill the other three seats
- Game playable from start to win without console errors

Out of scope (owned by M5):
- Aegean palette, JetBrains Mono / Inter typography
- Animations (card draw, slot fill, rule resolve, dice roll, status apply, VP claim)
- Sound, iconography, drag-drop, mobile/touch, settings UI

## M4: Smart bot (ISMCTS)

**Goal**: ISMCTS bot plays well enough that solo testing surfaces real design feedback. ISMCTS payoff design draws on M3 playtest signal — heuristics for "what counts as a good move" land after a human has played 20+ hands, not before.

Definition of done:
- `bots/ismcts.py` with information-set sampling from public state
- Configurable thinking budget; default 200ms/turn
- Beats `bots/random.py` significantly in self-play (target: 70%+ win rate over 100 games)
- Plays a full CLI game without crashing or hanging
- Sampling biased by visible info: chip counts, build history, label positions
- Logs decision rationale (for debugging) — top N candidate moves with projected VP delta

## M5: Polish

**Goal**: Looks and feels like the vision in `about.md`.

Definition of done:
- Aegean palette implemented per `aesthetic.md`
- Animations: card draw, slot fill, rule resolve, dice roll, status apply, VP claim
- Sound: all events from `aesthetic.md` audio table fire
- Iconography: pixel glyphs for all status tokens
- Drag-drop card placement
- Solo playthrough against 3 ISMCTS bots feels like the game described in `about.md`

## Out of scope (post-MVP)

- Multiplayer (engine→multiple clients sharing a session)
- Persistent meta-progression
- Card unlock system
- Replays
- Mobile / touch
- Tutorial
- Settings UI (chip costs, VP target tunable in-game)
- Custom rule decks / drafting
- Social features

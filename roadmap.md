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

## M3: Smart bot

**Goal**: ISMCTS bot plays well enough that solo testing surfaces real design feedback.

Definition of done:
- `bots/ismcts.py` with information-set sampling from public state
- Configurable thinking budget; default 200ms/turn
- Beats `bots/random.py` significantly in self-play (target: 70%+ win rate over 100 games)
- Plays a full CLI game without crashing or hanging
- Sampling biased by visible info: chip counts, build history, label positions
- Logs decision rationale (for debugging) — top N candidate moves with projected VP delta

## M4: Pixi client

**Goal**: Game playable end-to-end in browser.

Definition of done:
- `client/` repo bootstrapped with Vite + Pixi v8 + TypeScript
- Generated-types pipeline working (`scripts/regenerate-types.sh`)
- Websocket client connects to engine, receives state, renders
- Table layout per `aesthetic.md` (active rule center, opponents around, hand bottom)
- Cards: hover, drag, drop into rule slot
- UI greys out illegal cards (slot-compat-aware)
- Dice rolls visualized
- Rule resolves with visible state change
- Goal cards visible and update on claim
- Status tokens visible per opponent
- Game playable from start to win without console errors

## M5: Polish

**Goal**: Looks and feels like the vision in `about.md`.

Definition of done:
- Aegean palette implemented per `aesthetic.md`
- Animations: card draw, slot fill, rule resolve, dice roll, status apply, VP claim
- Sound: all events from `aesthetic.md` audio table fire
- Iconography: pixel glyphs for all status tokens
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

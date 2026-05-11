_Last updated: 2026-05-11 by orchestrator session — **M3 HUMAN-SEAT LOOP CLOSED**: RUL-67 (`StateBroadcast.legal_actions` additive field publishes the human's legal set; client renders buttons; click → `ActionSubmit`; game reaches END through the human seat) shipped via PR #71. Worker's scripted ws-client smoke confirmed 159 broadcasts, 24 human turns all carrying `legal_actions`, terminal carrying None, `phase=END` reached. Engine 513 tests passing; client typecheck/lint/build clean. Closes the deferred RUL-66 END-state rendering DoD bullet. **DiscardRedraw placeholder bites now**: clicking a discard button advances the turn without decrementing chips or redrawing — server's `pass_turn` placeholder mirrors `cli._drive_build_turn`. Next dispatchable: parallel fan of (a) server-side discard pipeline + (b) client decision-support rendering._

# Rulso — orchestrator bootstrap

This is the cold-start payload for a fresh orchestrator chat. Read after `CLAUDE.md` (auto-loaded), then dispatch.

Linear board: https://linear.app/rulso (team `RUL`, projects: Engine / Infra / Bots / Client / Design).

## Active milestones

| ID | Milestone | Goal | State |
|---|---|---|---|
| RUL-5 | M1: Engine core | 4-bot CLI game runs end-to-end, IF rules resolve, state machine sound | **Done** |
| RUL-15 | M1.5: Watchable engine | First moment the game is *real* | **Done** (closed 2026-05-10) |
| RUL-24 | M2: Full card set | Every card type and mechanic from cards.yaml works | **Done** (closed 2026-05-10) — gap-close set tracked as M2.5 below. |
| _(no parent)_ | **M2.5: Mechanic gaps** (pre-M3 sweep) | Close M2 mechanics that ship in code but not in play | **Done** (closed 2026-05-11) — RUL-57/60/62 in batch 1 + RUL-61/56 in batch 2. All 5 shipped; M2.5 follow-ups under RUL-24 cleared. |
| RUL-58 | **M3: Foundation/Minimal Client** | Human can read the board, make a meaningful decision, reach a winner | **In Progress (opened 2026-05-11)** — Substrate complete (RUL-63 envelope, RUL-64 server, RUL-66 client bootstrap, RUL-67 human-seat input loop closed). Next dispatchable: parallel fan of (a) server-side `DiscardRedraw` pipeline (visible bug now that humans can click discard) + (b) client decision-support rendering (card text, rule preview, goals visible, opponents' public state). Final M3 sub-issue: re-wire `bots/human` TTY through the WS. |
| RUL-59 | **M4: Smart bot (ISMCTS)** | ISMCTS surfaces real design feedback in solo play | **Backlog** — blocked-by RUL-58; payoff design draws on M3 playtest signal. |
| RUL-23 | Meta — orchestrator-authored cross-cutting commits | Permanent home for orchestrator commits | Permanent In Progress |

## Milestone reorder — ADR-0006 (2026-05-10)

The original `roadmap.md` ordering was M3 ISMCTS → M4 Pixi client → M5 polish. After M2 closed, the user attempted CLI playtesting via `rulso --human-seat 0` (RUL-52) and the prompt was unplayable — card IDs without text, no goal cards visible, no opponent state, 63 discard combos enumerated, no semantic preview of what completing the active rule would do. Bot strength is not the bottleneck; even with perfect ISMCTS opponents the human cannot make a meaningful decision against the current rendering. ADR-0006 reorders the post-M2 milestones:

| Milestone | Old | New |
|---|---|---|
| M3 | ISMCTS bot | **Foundation/Minimal Client** |
| M4 | Pixi client | **Smart bot (ISMCTS)** |
| M5 | Polish | Polish (unchanged) |

Foundation Client DoD bar is "ugly but playable": engine WS protocol + server, client bootstrap (Vite/Pixi/TS), type generation, decision-support rendering (full card text, semantic rule preview, goals visible, opponents' public state), click-to-play input, dice text. Polish (Aegean palette, animations, sound, drag-drop, iconography) all defers to M5.

## In flight

**Nothing in flight.** RUL-58 M3 substrate + input loop fully shipped (RUL-63 envelope, RUL-64 server, RUL-66 client bootstrap, RUL-67 human-seat input loop). The browser is now a playable seat: legal-action buttons render on every human BUILD broadcast, click → `ActionSubmit`, game reaches END through the human. Next dispatchable: **parallel fan** of two sub-issues — (a) server-side `DiscardRedraw` pipeline (engine-side; closes a now-visible placeholder bug); (b) client decision-support rendering (client-side; replaces JSON-stringified button labels with human-readable card text + rule preview). Touch surfaces are disjoint (engine vs client) — true parallel-safe. Final M3 sub-issue once both land: re-wire `bots/human` TTY through the WS so the same human-seat surface drives both browser and CLI playtest paths.

### RUL-67 ship summary (2026-05-11, PR #71)

| Decision | Locked | Rationale |
|---|---|---|
| Protocol extension | Additive `legal_actions: tuple[ClientAction, ...] \| None = None` on `StateBroadcast`; `PROTOCOL_VERSION` unchanged at `1` | ADR-0008 §Consequences pre-authorises additive variants — no version bump, no parser break for clients that ignore the field |
| Server population semantics | `_build_state_broadcast(state, human_seat)` helper threaded through every emit path; populates `legal_actions = tuple(enumerate_legal_actions(state, players[human_seat]))` only when `phase=BUILD AND active_seat==human_seat`; None otherwise | Re-uses the existing `enumerate_legal_actions` call (same one the server uses for `ILLEGAL_ACTION` validation) — no new enumeration surface, no drift risk. None on bot turns means client UI doesn't render stale buttons |
| Client UX | One button per legal action; label = `JSON.stringify(action)`; click → `ActionSubmit` + "OUTGOING" pre-block; submit-once safeguard disables peer buttons on click; buttons rebuild on every `StateBroadcast` (clear on bot turns); `ErrorEnvelope` does NOT clear the buttons (the human's turn is still in play until the next `StateBroadcast`) | Minimal viable input — JSON labels are playable but not friendly (decision-support text is the next sub-issue). Submit-once safeguard prevents double-fire on impatient double-click. Not-clearing-on-error preserves retry semantics |
| Smoke evidence | Worker ran a scripted ws-client driver (not a real browser): `broadcasts=159 human_turns=24 carrying_legal=24 end_seen=True end_legal_actions=None` | Same engine/client envelope contract end-to-end via the actual generated shapes; equivalent to a manual click-through. Worker provided incantations for a real-browser run if desired |

**Worker hand-back flags addressed**:

- **`DiscardRedraw` placeholder preserved**: server's `_apply_action` still treats `DiscardRedraw` as `pass_turn` (mirrors `cli._drive_build_turn`). Worker took the explicit "otherwise leave the placeholder" branch from the hand-over stop condition — clicking a discard button advances the turn without decrementing chips or redrawing cards. **Follow-up filed below** as a now-visible bug; was registered in earlier sweeps as "wait for client-side discard surface to be specced", which has now arrived
- Browser-driven smoke skipped in favour of scripted ws driver: scripted run exercises identical envelope shapes; equivalent verification. No follow-up
- `npm run lint` from inside `client/` has a pre-existing config-path quirk (worker noted, not introduced by this PR). The pre-commit hook from repo root is clean. **Follow-up note**: investigate the cwd-quirk separately if it bites another contributor

**Cross-cutting fixes landed via this RUL-23 sweep**:

- `docs/engine/readme.md`: `_Last edited:` bumped; `protocol.py` row notes the additive `legal_actions` field + PROTOCOL_VERSION-unchanged invariant; `server.py` row notes the `_build_state_broadcast` helper + the BUILD-phase + active-seat guard; `test_server.py` row extended with the new coverage
- `docs/client/readme.md`: `_Last edited:` bumped; `main.ts` row notes the button rendering + submit-once safeguard + ErrorEnvelope-doesn't-clear semantics; `net.ts` row notes the new `send` export; smoke section now describes the closed loop + the two open caveats (DiscardRedraw placeholder; JSON-stringified labels pending decision-support text)
- STATUS.md re-anchored to post-RUL-67 (this entry)

### Open follow-ups post-RUL-67

- **Server-side `DiscardRedraw` pipeline** (NOW VISIBLE BUG, not just a placeholder): clicking a discard button on the human seat advances the turn without decrementing chips or replacing cards. Engine-side scope: extend `server._apply_action` (or `cli._drive_build_turn`'s shared helper if extracted) to actually execute the discard via `cards.deal_replacements` (or the equivalent), decrement chips by `len(card_ids) * DISCARD_COST`, broadcast the result. Test that round-trips `DiscardRedraw` end-to-end. **Filing as next dispatchable.**
- **Client decision-support rendering** (M3 fan sibling): replace JSON-stringified button labels with human-readable card text + semantic rule preview ("Play THE LEADER → SUBJECT slot"); render goal cards face-up; opponents' chips/VP/status tokens visible. Touch surface: client-side only (`main.ts` rendering helpers + theme constants). Parallel-safe with the discard pipeline. **Filing as next dispatchable.**
- **`_OP_ONLY_COMPARATOR_NAMES` duplication** between `cli.py` and `server.py` — promote to `legality.py` or `effects.py`. Low priority parallel-safe one-PR refactor; not blocking
- **TS type-gen `state.py` coverage** carried forward from RUL-66 — extend `scripts/regenerate-types.sh` to introspect `rulso.state` if rendering needs richer state types directly (vs unwrapping `StateBroadcast.state`); not a blocker
- **`npm run lint` cwd quirk** (RUL-67 worker note) — investigate separately if another contributor bumps it

### RUL-66 ship summary (2026-05-11, PR #70)

| Decision | Locked | Rationale |
|---|---|---|
| Generator | `pydantic-to-typescript` (engine dev-dep) → `json-schema-to-typescript` (client dev-dep, `client/node_modules/.bin/json2ts`); two-step pipeline in `scripts/regenerate-types.sh` | `pydantic2ts` introspects `BaseModel` subclasses cleanly; `json2ts` does the JSON-Schema → TS conversion with discriminator support. Single canonical pipeline, both deps pinned, idempotent re-runs. |
| `TypeAdapter` aliases | Hand-curated `client/src/types/envelopes.ts` re-exports `ServerEnvelope` / `ClientAction` / `ClientEnvelope` with literal-typed `type` / `kind` fields | `pydantic2ts` only surfaces `BaseModel` subclasses, not module-level `Annotated[Union[...], Field(discriminator=...)]` aliases (those are `TypeAdapter` aliases, not `BaseModel`s). The hand-curated wrapper is small (~40 lines), stable per ADR-0008, and produces the discriminated-union narrowing TypeScript expects. |
| `biome.json` location | Repo root (not `client/`) | Pre-commit hook runs from repo root with cwd=root; `npm run lint` runs from `client/` with cwd=client/. Biome walks ancestors from cwd until it finds `biome.json` — placing it at root means both invocation paths converge on the same config. Without this, the hook reverts to Biome defaults (tab indent) and reformats client files away from the project's space-indent style. |
| Top-level `scripts/` | New | First user; hand-over named the path explicitly. `scripts/regenerate-types.sh` is the only inhabitant. |
| `docs/client/readme.md` | New (worker-authored, hand-over allowed) | Mirrors `docs/engine/readme.md` shape (surface table + commands + smoke); orchestrator-owned `docs/readme.md` and `docs/engine/readme.md` not touched. |
| `tech.md §Type generation` | Promoted from "proposed" to shipped | The pipeline went from sketch to live; doc convention requires `tech.md` reflect actually-shipped state. §"How to run" unchanged. |
| END-state rendering DoD | **Unsatisfiable by construction; deferred** | Read-only client; human seat (0) blocks indefinitely on first BUILD turn (`Pass` is server-side-only on empty legal sets per ADR-0008; chips≥5 keeps discard branch non-empty so legal set never empties). Worker proved protocol path healthy via one-shot Node driver (7800 envelopes round-tripped). END-state proof falls out naturally of the next sub-issue (input). Workflow lesson captured (2026-05-11 entry on DoD-scope symmetry). |

**Worker hand-back flags addressed**:

- DoD bullet "terminal `StateBroadcast` … status flips to closed cleanly" was unsatisfiable from inside the ticket's read-only scope. **Decision**: accept partial DoD; END-state rendering covered by the next sub-issue (input). New workflow lesson captured: DoD bullets must be satisfiable from inside the ticket's scope.
- `biome.json` at root rather than `client/`: correct call (hook + npm cwd convergence). Documented in this RUL-23 sweep — `docs/engine/readme.md` "Pre-commit hook contract" expanded; `docs/client/readme.md` surface table fixed (worker labelled the row `client/biome.json` — actual path is `biome.json` at root).
- New top-level `scripts/`: expected; hand-over explicit. No follow-up.
- `tech.md §Type generation` promoted: correct call; tech.md is public source of truth, must reflect shipped state.
- `client/src/types/envelopes.ts` hand-curated: correct call given pydantic2ts limitation. Stable per ADR-0008. Documented in `docs/client/readme.md` line 19.

**Cross-cutting fixes landed via this RUL-23 sweep**:

- `docs/client/readme.md`: corrected `client/biome.json` row → `biome.json` (repo root) with the hook/npm convergence rationale inline.
- `docs/engine/readme.md`: `_Last edited:` bumped to post-RUL-66; "Pre-commit hook contract" section expanded to call out that `biome.json` lives at the repo root and Biome's ancestor-walk is what makes hook+npm converge on the same config.
- `docs/workflow_lessons.md`: new entry 2026-05-11 — DoD-scope symmetry rule (DoD bullets must be satisfiable from inside the ticket's scope; the END-state rendering bullet on a read-only client was the precedent). Template-worthy: yes — promotes to global `CLAUDE.md` as a ticket-shape rule alongside the existing data-loadable / data-observable split.
- STATUS.md re-anchored to post-RUL-66 (this entry).

### Open follow-ups post-RUL-64/65/66

- **`_OP_ONLY_COMPARATOR_NAMES` duplication** between `cli.py` and `server.py` — promote to `legality.py` (or `effects.py`). **Parallel-safe one-PR refactor**, low priority.
- **Server-side `DiscardRedraw` placeholder**: `server.py` currently treats `DiscardRedraw` as `pass_turn`. Wire the full discard pipeline when client-side discard UX lands (likely the next M3 sub-issue after input).
- **TS type-gen `state.py` coverage**: RUL-66's pipeline emits the `GameState` transitive closure via `BaseModel` subclass introspection — but the type-gen script currently introspects `rulso.protocol` only. If the rendering sub-issue needs richer state types directly (vs unwrapping `StateBroadcast.state`), extend the script to introspect `rulso.state` too. Not a blocker — the protocol envelope's `state: GameState` field already pulls the closure.

### RUL-64 + RUL-65 ship summary (2026-05-11, PRs #68 / #69)

| Ticket | PR | Notes |
|---|---|---|
| RUL-65 | #68 | Action surface promoted from `bots.random` to `legality.py`. Worker hit the predictable cycle (`bots.random → legality` already imports `can_attach_joker`), made the right judgment call: also moved `_enumerate_plays` / `_enumerate_discards` / `_OP_ONLY_*` into `legality` rather than hand back. `bots.random.choose_action` now re-imports from `legality`. Single source for `protocol.ClientAction` Pydantic class identity (ADR-0008's "no drift" guarantee preserved). 499/499 green; clean break, no re-export shims. `docs/engine/legality.md` rewritten in this RUL-23 sweep to reflect the new role. |
| RUL-64 | #69 | Engine WS server. `async def run_server(*, host, port, seed, human_seat)` + sync `def main()` exposed via `rulso-server` console script. Per-connection model: a reader coroutine drains envelopes (`PROTOCOL_INVALID` / `NOT_YOUR_TURN` rejection on the wire) and queues legitimate `ActionSubmit`s for the game loop, which validates legality at apply time and replies with `ILLEGAL_ACTION` if the queued action is no longer valid. Reader and game loop yield once after every queue-put / broadcast (`await asyncio.sleep(0)`) so the two stay in lockstep — without these yields the bot rotation outruns reader scheduling on fast localhost and rejection-code attribution becomes nondeterministic (documented in module + reader docstrings). Disjoint-rng pattern preserved (`seed / seed^0x5EED / seed^0xD1CE / seed^0xEFFC`). 11 new tests in `test_server.py` covering handshake, bot-only progress, action round-trip, all three rejection codes, end-to-end termination. |

**Merge sequence**: RUL-65 merged first (clean against pre-RUL-64 main); RUL-64 rebased in-place (no file conflicts — fully disjoint surfaces) but its `server.py` + `test_server.py` imports needed re-pointing from `bots.random` → `legality` for the moved symbols. Orchestrator pushed `RUL-64: re-point action-shape imports to legality.py post-RUL-65` to RUL-64's branch (mechanical 4-line fixup; squash-merged into the main RUL-64 commit). Pattern: same as the 2026-05-10 behavioural-substrate cascade lesson (CLEAN merge mechanics is necessary but not sufficient when a sibling has landed a contract change) — caught proactively this time, not post-merge.

**Cross-cutting fixes landed via this RUL-23 sweep**:
- `docs/engine/readme.md`: `legality.py` row expanded (now owns full action surface + internal enumerators); `server.py` stub → live with per-feature description; `protocol.py` row updated to cite `legality` as the action-shape source (was `bots.random`); `bots/random.py` row trimmed to its post-RUL-65 surface (`choose_action`, `select_purchase`, `_find_player`); `bots/human.py` row updated to cite `legality.enumerate_legal_actions`; new `test_server.py` row added with the `pytest-asyncio` cwd caveat. `_Last edited:` bumped.
- `docs/engine/legality.md`: full rewrite — pre-RUL-65 doc only covered `first_card_of_type` (one helper); post-RUL-65 doc covers the full action vocabulary, enumeration helper, internal enumerators, and the `bots.random ↔ legality` cycle-avoidance rationale. References every test that exercises the surface.
- `docs/workflow_lessons.md`: new entry 2026-05-11 — `uv run --project engine pytest` from project root silently skips async tests because pytest's rootdir discovery doesn't piggyback on `--project`. Verification incantation is `cd engine && uv run pytest` OR `uv run --project engine pytest engine/tests`. Template-worthy: maybe (extends the existing `feedback_readme_cwd_context.md` rule to invocations whose rootdir resolution drives configfile discovery).
- STATUS.md re-anchored to post-RUL-64/65 (this entry).

**Worker hand-back flags addressed**:

- RUL-65: worker moved `_enumerate_*` helpers into `legality` to dodge a circular import (DoD literally said they stay in `bots.random`). Right call — moving them was the *only* way to avoid the cycle without leaving behaviour broken. Spirit honoured (canonical home in `legality`, bot-policy bias/RNG in `bots.random`). Accepted; no follow-up.
- RUL-64: `_OP_ONLY_COMPARATOR_NAMES` is duplicated between `cli.py` and `server.py` as a private constant. Worker flagged as a tidy candidate. **Status**: open follow-up — minor; promote to `legality.py` when the next ticket touches that constant. Not blocking.
- RUL-64: `pytest-asyncio>=1.0` added as a dev dep + `asyncio_mode = "auto"` in `engine/pyproject.toml [tool.pytest.ini_options]`. First asyncio test in the suite. Caused the cwd-discovery surprise above; lesson captured.
- RUL-64: `DiscardRedraw` is treated as `pass_turn` on the server, matching `cli._drive_build_turn`'s placeholder. Full discard pipeline still belongs to a later ticket. **Status**: open follow-up — wire when client-side discard UX lands.
- RUL-64: `bots.random` was a *fourth* in-tree consumer of the action shapes when the worker shipped (`cli`, `bots/human`, `protocol`, `server`). Worker correctly stop-conditioned the inline refactor per RUL-64's "Out of scope" — RUL-65 lands the promotion in its own PR. The orchestrator-pushed fixup re-pointed `server.py`'s imports to `legality` post-merge.

### Open follow-ups post-RUL-64/65

- **`_OP_ONLY_COMPARATOR_NAMES` duplication** between `cli.py` and `server.py` — a private constant the random bot also uses (the `_OP_ONLY_*` set was moved to `legality.py` by RUL-65). The two driver modules redefine it locally. Promote to `legality.py` (or `effects.py`, where `is_operator_modifier` lives) and have both drivers import it. **Parallel-safe one-PR refactor**, low priority — file when a worker has a side-task slot.
- **Server-side `DiscardRedraw` placeholder**: `server.py` currently treats `DiscardRedraw` as `pass_turn` (matching `cli._drive_build_turn` at the time of writing). The full discard pipeline will land with the M3 client-side discard UX. **Wait for client-side discard surface to be specced** before filing.
- **TS type generation pipeline** (`scripts/regenerate-types.sh` + `client/src/types/`): lands as its own M3 sub-issue per the original plan. Filed alongside or after client bootstrap — sequencing TBD on bootstrap-ticket scope.

### RUL-63 ship summary (2026-05-11, PR #66)

| Decision | Locked | Rationale |
|---|---|---|
| Envelope structure | Server→client `Hello` / `StateBroadcast` / `ErrorEnvelope` tagged on `type`; client→server `ActionSubmit` tagged on `type`, inner action tagged on `kind` (existing engine convention — no namespace collision) | One ADR (ADR-0008). Cadence is a direct consequence of envelope shape under MVP. |
| Broadcast cadence (MVP) | Full `StateBroadcast` on every `GameState` mutation. No diff. | `tech.md` informal hint promoted to ratified shape; coalescing/diff get a future ADR if and when they land. |
| Action-submit shape | (b) Structured. `ClientAction = PlayCard \| PlayJoker \| DiscardRedraw`, **imported verbatim** from `rulso.bots.random` (no redefinition, no drift). | Click-driven UI builds structured payloads naturally; server re-enumerates legal actions and validates structural equality. |
| `Pass` handling | Excluded from `ClientAction`. Server picks `Pass` automatically on empty `enumerate_legal_actions`. | Closes a turn-skipping loophole; matches `bots/human` EOF behaviour. |
| `roll_choice` | Folded into `PlayCard.dice` (existing engine field, ADR-0002 precedent). | One less envelope variant; the dice choice already lives where it's consumed. |
| `shop_purchase` / `claim_goal` envelopes | Omitted. SHOP purchase is engine-internal (`select_purchase` returns an offer index); goal claims fire automatically in `enter_resolve` (RUL-46). | Additive — future variants extend the `Annotated` union with no `PROTOCOL_VERSION` bump. |
| `end_of_game` envelope | Not modelled. Terminal state is `StateBroadcast` with `winner` set + `phase=END`. | Simpler; clients already parse state-broadcast every transition. |
| Parser helper | None. `TypeAdapter(ServerEnvelope).validate_json(raw)` is the idiomatic path the server ticket will use directly. | Avoids redundant wrapper. |
| `PROTOCOL_VERSION` | `int = 1`. | Bump only on incompatible envelope changes; additive variants / new enum values do not bump. |

**Cross-cutting fixes landed via this RUL-23 sweep**:
- `docs/engine/readme.md`: `protocol.py` row promoted stub → live with ADR-0008 summary; `test_protocol.py` row added; `_Last edited:` bumped.
- STATUS.md re-anchored to post-RUL-63 (this entry).
- ADR-0008 added to active ADRs.

**Worker hand-back flags addressed**:
- One ADR vs two: worker picked one; orchestrator ratifies. Cadence is shape's consequence under MVP; a future tuning ticket gets its own ADR if coalescing/diff machinery lands.
- Narrowed envelope set (vs ticket AC listing shop_purchase + claim_goal + roll_choice "at minimum"): worker correctly cross-referenced against the actual engine action surface and pruned the list. Right call — orchestrator originally drafted the AC from the cards.yaml surface, not the action surface. `enumerate_legal_actions` does not return `shop_purchase` or `claim_goal`. Ticket AC was wrong; worker corrected it. The omitted variants are forward-compatible per ADR-0008 §Consequences (one new `BaseModel` subclass + one new union member when needed).
- No `parse_inbound()` helper: idiomatic `TypeAdapter.validate_json` is what the server ticket will call.
- No `end_of_game` envelope: terminal state is `StateBroadcast` with `winner` set + `phase=END` — simpler, no redundant terminal-message machinery.

### Open follow-ups post-RUL-63 (resolved by this sweep)

- ~~**Promote `bots.random` action shapes to `legality.py` or `actions.py`**~~ — **DONE 2026-05-11 (RUL-65, PR #68)**. `legality.py` is now the engine's canonical action surface.
- **TS type generation pipeline** (`scripts/regenerate-types.sh` + `client/src/types/`): lands as a sibling/successor of client-bootstrap sub-issue per the M3 fan plan. ADR-0008 §Consequences notes the discriminated-union pattern Pydantic emits maps cleanly to TypeScript tagged unions via `pydantic-to-typescript` / `datamodel-code-generator`. **Carried into the post-RUL-64/65 follow-ups list above.**

### Backlog sweep (2026-05-11, this session)

Stale tickets reconciled before M3 open:

| Ticket | Was | Now | Reason |
|---|---|---|---|
| RUL-22 | In Progress | Done | Shipped via PR #17 (2026-05-09); the documented orchestrator-PR-prefix gotcha — Linear auto-closed it on a meta-commit, was flipped back to Todo, and never re-closed. Workflow lesson 2026-05-09 entry covers the gotcha. |
| RUL-36 | Todo | Duplicate of RUL-39 | "Effect dispatcher" — shipped as RUL-39 (Phase 3 D, PR #37). |
| RUL-37 | Todo | Duplicate of RUL-40 | "status.py apply/decay" — shipped as RUL-40 (Phase 3 E, PR #40). |
| RUL-38 | Todo | Duplicate of RUL-41 | "ANYONE / EACH_PLAYER scope_mode" — shipped as RUL-41 (Phase 3 F, PR #35). |

RUL-1 / RUL-2 / RUL-3 / RUL-4 (Linear onboarding tickets) are already archived; left alone.

### M2.5 ship summary (2026-05-11, PRs #59/#60/#61/#63/#64)

Batch 1 (parallel fan, dispatched and merged in same session):

| Ticket | PR | Notes |
|---|---|---|
| RUL-57 | #59 | `docs/engine/bots.md` PlayCard rules: replaced stale "two entries: dice=1 and dice=2" line with the ADR-0002 split (OP-only → single `dice=2` entry; M1.5 baked-N legacy → dual entries). Doc-only. |
| RUL-60 | #60 | `effects.resolve_if_rule` iterative branch intersects `scoped` with MARKED holders when ≥1 hold MARKED; falls back to unchanged scope at 0. ANYONE / singular SUBJECTs unaffected. 7 new tests in `test_effects_marked_scope.py`. |
| RUL-62 | #61 | ADR-0007 locks **shape 2** (card-buy via existing `_ShopEntry.payload_type` route). 7-offer M2.5 starter table proposed. Every identifier cross-referenced against engine. |

Batch 2 (sequential, ordered to avoid baseline-rebase thrash):

| Ticket | PR | Notes |
|---|---|---|
| RUL-61 | #63 | Status-data completeness: `eff.marked.apply` + `eff.chained.clear` appended at head of `cards.yaml effect_cards:` (preserves seed-0 first-12-pops byte-equality). Floor 7 → 6 ratified — full M2 status vocabulary live; seed 4 flipped to cap-hit (deck depth 12 → 14 shifts recycle timing). `docs/engine/m2-smoke.md` re-baselined to winners 0/1/3/5/7/9. First worker stop-conditioned correctly (workers don't bump smoke floors unilaterally); orchestrator authorised option (a) on re-dispatch. |
| RUL-56 | #64 | SHOP content: 7-offer pool per ADR-0007 with **price-tuned** gradient `10/12/11/11/11/11/12` (within ADR-0007's 5-12 range; tuning explicitly authorised by ADR-0007 §"Pricing rationale"). Un-tuned ADR-0007 prices yielded 4/10 winners; tuning held the 6/10 post-RUL-61 floor with the identical winner set (0/1/3/5/7/9). First worker stop-conditioned correctly when un-tuned prices dropped the floor; orchestrator authorised option (b) — price tune within band, not floor bump. Mechanism: `bots.random.select_purchase` is "cheapest-affordable, ties by lowest index"; tight 10-12 band keeps every offer rarely affordable in rounds 3/6 after BURN + 5-chip discards. |

**Cross-cutting fixes landed via this RUL-23 sweep**:

- `docs/engine/readme.md`: test_shop.py + test_m2_watchable.py rows extended to cite RUL-56/RUL-61 wiring; `_Last edited:` bumped.
- `STATUS.md`: M2.5 marked Done; re-anchored to post-M2.5 state.
- `docs/workflow_lessons.md`: new entry — "ADR's own tuning clause: worker missed the authorisation, orchestrator caught it on the merge sweep" (RUL-56 specifically; template-worthy maybe).

Main: **479 tests passing**, ruff clean. Deterministic M2 watchable smoke at **6/10 winners** (seeds 0/1/3/5/7/9 win; 2/4/6/8 cap-hit) on PLAY_BIAS=0.75 with full M2 status vocabulary + active SHOP content.

## Audit findings — closed by M2.5 (2026-05-10 audit; closed 2026-05-11)

Cross-referenced `engine/src/rulso/{status,effects,goals}.py` against `design/status-tokens.md` and `cards.yaml`. All gaps closed by M2.5:

- **BURN** — apply (`APPLY_BURN`) ✓, clear (`CLEAR_BURN`) ✓, tick (`status.tick_round_start`) ✓, BLESSED interaction ✓, NOUN read (`BURN_TOKENS`) ✓. _Unchanged._
- **MUTE** — apply (`APPLY_MUTE`) ✓, natural decay at `round_start` step 2 ✓, blocks MODIFIER plays in `bots.random._enumerate_plays` ✓. _Unchanged._
- **BLESSED** — apply (`APPLY_BLESSED`) ✓, on-use clear via `consume_blessed_or_else` ✓, integrated at `LOSE_CHIPS` and BURN tick ✓. _Unchanged._
- **MARKED** — apply (`APPLY_MARKED` handler) ✓, natural decay at `resolve` step 10 ✓, **`eff.marked.apply` in `cards.yaml effect_cards:`** ✓ (RUL-61, PR #63), **EACH_PLAYER scope narrowing** ✓ (RUL-60, PR #60). Decorative-only state closed.
- **CHAINED** — apply (`APPLY_CHAINED`) ✓, clear handler (`CLEAR_CHAINED`) ✓, **`eff.chained.clear` in `cards.yaml effect_cards:`** ✓ (RUL-61, PR #63), goal-claim eligibility filter at `goals.py:123` ✓, `THE_FREE_AGENT` predicate read ✓. Permanent-state-once-chained closed.
- **SHOP** substrate ✓ (RUL-51), **content** ✓ (RUL-56, PR #64; 7-offer pool at tuned 10/12/11/11/11/11/12 gradient per ADR-0007). Empty-pool short-circuit closed.
- **All other M2 mechanics** (WHEN/WHILE lifecycle, JOKER variants, polymorphic NOUN reads, comparator dice, operator MODIFIER fold, all 4 floating labels, goal claims) — wired and consumed.

## Wave 4 ship summary (2026-05-10, PRs #54/#55/#56)

### Wave 4 ship summary (2026-05-10, PRs #54/#55/#56)

| ID | PR | Notes |
|---|---|---|
| RUL-53 | #54 | `docs/engine/bots.md` refresh: PlayJoker section + JOKER variant table (PERSIST_WHEN/WHILE/DOUBLE/ECHO), operator-MODIFIER skip rules inline, `enumerate_legal_actions` public-helper section, `bots.human.select_action` section. Doc-only. Out-of-scope drift flagged → RUL-57. |
| RUL-51 | #55 | Real `Phase.SHOP` handler replacing `NotImplementedError`. Additive `ShopOffer` model + `shop_pool` / `shop_offer` / `shop_discard` fields on `GameState`; cadence `round_number % SHOP_INTERVAL == 0`; buy order `(vp asc, chips asc, seat asc)` per `design/state.md` (overrode hand-over's stale "Player.id" tie-break — canonical source wins); recycle-on-empty pool follows the RUL-54 disjoint-rng pattern (`ValueError` if `rng=None` on the recycle path). 13 new tests in `test_shop.py`; one existing test edited (`test_advance_from_shop_raises_not_implemented` → `…with_empty_offer_resumes_round_start`). `cards.yaml shop_cards:` ships empty — SHOP short-circuits in CLI; smoke output byte-for-byte unchanged. Content TBD in RUL-56. |
| RUL-55 | #56 | Lever A only: `PLAY_BIAS = 0.85 → 0.75` in `bots/random.py`. Deterministic baseline lifts 5/10 → 7/10 (seeds 0/1/3/4/5/7/9 win; 2/6/8 cap-hit); stable at rounds=300. `_MIN_WINNERS` raised 5 → 7 (no slack); `docs/engine/m2-smoke.md` baseline + rationale + stop-conditions all re-anchored to 7/10. Lever B (deck rebalance) probed and rejected — every config hitting ≥7/10 reshuffles seed-0 deals and breaks `test_cards_loader`, `test_determinism.test_recycle_path`, `test_jokers.test_full_game_round_trip_with_persistent_when_joker` via the goal-pool shuffle cascade. Rebased onto post-RUL-51 main; full suite (468 tests) re-verified before merge. |

**Cross-cutting fixes landed via this RUL-23 sweep**:
- `docs/engine/readme.md`: row added for `test_shop.py`; `cards.py`, `rules.py`, `bots/random.py`, `test_m2_watchable.py` description rows refreshed for Wave 4 wiring (SHOP loader, SHOP phase handler, `select_purchase`, `PLAY_BIAS = 0.75`, 7/10 winner floor). `_Last edited:` bumped to Wave 4.
- `STATUS.md`: re-anchored to post-M2-close state; M2 milestone marked Done; RUL-56/RUL-57 follow-ups registered.
- `docs/workflow_lessons.md`: new entry 2026-05-10 — deck-composition fragility beyond `_drive_to_first_build` (goal-pool shuffle cascade breaks `test_cards_loader` + `test_jokers.test_full_game_round_trip_with_persistent_when_joker` + `test_determinism.test_recycle_path` when the deck reshuffles). Companion to the existing "deck-size fragility in test helpers" lesson from RUL-31 — the fragility is wider than tests-that-use-`_drive_to_first_build`.

**Worker hand-back flags addressed**:
- RUL-51: hand-over said tie-break by `Player.id`; canonical `design/state.md` says VP → chips → seat. Worker correctly followed state.md. **Decision**: keep state.md as the source of truth; the hand-over template was wrong. No ADR needed.
- RUL-51: `shop_cards:` empty in `cards.yaml` — followed the minimal-stub path. Content + payload-type ADR deferred to RUL-56.
- RUL-53: `bots.md` PlayCard rules still claim all comparator MODIFIERs enumerate both dice modes; RUL-42 changed LT/LE/GT/GE/EQ to default 2d6 only. **Filed RUL-57** as a sibling docs follow-up.
- RUL-55: hand-over referenced `engine/data/cards.yaml`; actual path is `design/cards.yaml`. **Memory rule saved** (`feedback_cards_yaml_path.md`) so future hand-overs cite the correct path.

**Outstanding follow-ups**:
- RUL-56: SHOP content (populate `shop_cards:` + payload-type ADR) — **Backlog**, depends on a payload-semantics decision; not blocked but probably waits for M3 playtest signal.
- RUL-57: `bots.md` dice-mode drift — **Backlog**, parallel-safe docs chore.
- RUL-35: M2 watchable smoke — **DONE 2026-05-10 (PR #52)**.
- RUL-51 / RUL-53 / RUL-55: Wave 4 — **DONE 2026-05-10**.

### RUL-35 ship summary (2026-05-10, PR #52, recap)

- **Test-side instrumentation** (no production-module edits): module-scoped fixture wraps `effects.resolve_if_rule`, `persistence.check_when_triggers`, `persistence.tick_while_rules`, `goals.check_claims` as pure observers; restored in `try/finally`. 42/42 green in same pytest session as M1.5 + determinism — no leakage.
- **Empirical baseline pinned**: 5/10 winners → **lifted to 7/10 by RUL-55** (PLAY_BIAS 0.85 → 0.75).
- **Lifecycle floors** at sweep-aggregate ≥1 (observed counts: 843 WHEN, 1992 WHILE, 28 goal-VP, 235 chip-delta).
- **README cwd form preserved**: `uv run --project engine rulso …`.

### RUL-54 substrate fix (2026-05-10, PR #50, recap)

RUL-35's first dispatch correctly stop-condition'd before any code change. Worker probed 5 × 10-seed sweeps and saw winner counts varying 4–6/10 across identical invocations. Root cause: `cli.py:85` called `advance_phase(state)` without rng for `ROUND_START`, and RUL-47's `enter_round_start` fell back to an unseeded `random.Random()` whenever the 12-card effect deck recycled (round ~13). Two latent twins at `enter_resolve` step 12 and `_refill_hands` used the same `rng or random.Random()` fallback shape.

RUL-54 fixed all three sites: shape (b) — `rng=None` tolerated when the reshuffle does not fire; `ValueError` at the reshuffle site otherwise. New disjoint stream `effect_rng = random.Random(seed ^ 0xEFFC)` slots into the CLI alongside `rng` / `refill_rng` (0x5EED) / `dice_rng` (0xD1CE). 4 new tests including `test_determinism.py` byte-identical-stdout invariant.

**Lesson captured** (`docs/workflow_lessons.md` 2026-05-10): a behavioural-substrate cascade at *depth* — RUL-47's fallback only bit at round 13, escaping a PR review that read the diff and confirmed all existing fixtures stayed green. Three substrate axes proposed for the global protocol: code-substrate (file shape), behavioural-substrate (function contract), conditional-substrate (runtime-conditional path). RUL-47 hit all three.

### Wave plan

- **Wave 1 (DONE 2026-05-10)**: RUL-47 (round-flow effect-deck draw — substrate wiring; PR #44) + RUL-48 (cards-inventory.md noun.hits text fix; PR #42) + RUL-50 (sync design/state.md JOKER step-reorder + ECHO conditional; PR #43). RUL-23 sweep: PR #45.
- **Wave 2 (DONE 2026-05-10)**: RUL-49 (BLESSED chip-loss + BURN tick; PR #46) + RUL-52 (CLI human-seat; PR #47). Behavioural-substrate cascade contained in PR #46 (single fixture amended in-PR with explanatory comment; 8 new tests cover the BLESSED+chip-loss matrix). UI/driver work in PR #47 was strictly additive (kw-only `human_seat=None` defaults; existing CLI smoke tests passed unchanged). RUL-23 sweep: this PR.
- **RUL-54 (substrate fix, DONE 2026-05-10)**: PR #50. Thread `effect_rng` through CLI → `enter_round_start`; eliminate `rng or random.Random()` fallbacks at three sites (now raise `ValueError` at the reshuffle path). Disjoint stream `seed ^ 0xEFFC`. New `test_determinism.py` exercises post-round-13 invariants. Unblocked RUL-35.
- **Wave 3 (gate, solo) — DONE 2026-05-10**: RUL-35 — M2 watchable smoke (PR #52). Landed at the hand-over's "acceptable down to" boundary (5/10 deterministic winners). Phase 3.5 polish ticket filed as RUL-55 to push the floor up via bot heuristic and/or deck rebalance.
- **Wave 4 (DONE 2026-05-10)**: parallel fan closes M2 + clears doc debt. PRs #54 (RUL-53), #55 (RUL-51), #56 (RUL-55). Per-ticket detail in the "Wave 4 ship summary" table above.
- **Open after Wave 4**: M3 ISMCTS scoping. Lean is to defer M3 until the user has playtested via RUL-52 (`uv run --project engine rulso --seed 5 --rounds 100 --human-seat 0`) — the playtest data shapes ISMCTS payoff. RUL-56 (SHOP content) is the only non-M3 substrate that can land first; whether it should is a design call.

### Wave 2 — final state (2026-05-10)

| ID | PR | Notes |
|---|---|---|
| RUL-49 | #46 | BLESSED wired into `effects._lose_chips` (LOSE_CHIPS handler) and `status.tick_round_start` (BURN tick). Per-target consumption; zero-magnitude losses do not consume BLESSED; BURN tokens persist when BLESSED cancels the drain. `design/state.md` BLESSED line amended to make the BURN-tick interaction explicit (resolves `design/status-tokens.md` flag 1). 8 new tests in `test_status.py`. Late-import alias renamed (`from rulso import status as _status` → `from rulso import status`) so `_lose_chips` can call into it; circular bootstrap unaffected. |
| RUL-52 | #47 | New `bots/human.py` (TTY action driver). New public helper `bots.random.enumerate_legal_actions(state, player)` — reuses random's predicate set without `PLAY_BIAS` weighting; available to any future driver (replay, ISMCTS rollouts). `cli.run_game` and `cli.main` gain kw-only `human_seat: int|None` and `human_stdin: TextIO|None` (default `None` — baseline preserved byte-for-byte). 7 new tests including parametrised seat-index coverage. `--human-seat 0..3` is the CLI flag. |

**Cross-cutting fixes landed via this RUL-23 sweep**:
- `docs/engine/readme.md` index: rows added for `bots/human.py` and `test_cli_human_seat.py`; `bots/random.py` and `status.py` descriptions updated to reflect Wave 2 wiring (`enumerate_legal_actions` public helper + BLESSED chip-loss + zero-magnitude exclusion). `_Last edited:` bumped to Wave 2.

**Worker hand-back flags addressed**:
- RUL-52 worker: `legality.legal_actions(state, player_id)` was named in the hand-over but doesn't exist. Worker correctly used `bots.random.enumerate_legal_actions` instead. **Decision**: keep as-is; the new helper is now the canonical legal-action-enumeration surface. No follow-up filed.
- RUL-52 worker: `docs/engine/bots.md` is stale (predates RUL-43/45 — no `PlayJoker`, no operator-MODIFIER skip rules). Filed **RUL-53** as a Wave 4 docs chore.

**Outstanding follow-ups**:
- RUL-35: M2 watchable smoke — **DONE 2026-05-10 (PR #52)**.
- RUL-51: SHOP round — **Wave 4**, parallel-safe with RUL-53 + RUL-55.
- RUL-53: refresh `docs/engine/bots.md` for Phase 3 + Wave 2 — **Wave 4 docs chore**, parallel-safe.
- RUL-54: rng determinism substrate fix — **DONE 2026-05-10 (PR #50)**.
- RUL-55: Phase 3.5 polish (push winners above 5/10) — **Wave 4**, parallel-safe with RUL-51 + RUL-53.

### Phase 3 fan — final state (2026-05-10)

| ID | Letter | PR | Notes |
|---|---|---|---|
| RUL-39 | D | #37 | Effect dispatcher + `register_effect_kind` registry hook |
| RUL-40 | E | #40 | `status.py` + 7 effect-kind registrations (5 DoD + APPLY_MARKED + CLEAR_CHAINED); BLESSED chip-loss wiring shipped in Wave 2 (RUL-49) |
| RUL-41 | F | #35 | ANYONE / EACH_PLAYER scoping per ADR-0003 (existential = subset-fire-once, iterative = per-player loop) |
| RUL-42 | G | #38 | Comparator dice (ADR-0002) |
| RUL-43 | H | #36 | Operator MODIFIER fold (ADR-0004) |
| RUL-44 | I | #34 | Polymorphic NOUN reads |
| RUL-45 | J | #41 | JOKER attachment (PERSIST_WHEN/WHILE/DOUBLE/ECHO); state.md sync shipped in Wave 1 (RUL-50) |
| RUL-46 | K | #39 | Goal-claim engine; ADR-0005 ratifies retype |

### Wave 1 — final state (2026-05-10)

| ID | PR | Notes |
|---|---|---|
| RUL-47 | #44 | Round-flow effect-deck draw: `enter_round_start` step 6 pops from `effect_deck`; `enter_resolve` step 10 pushes to `effect_discard`; rule-failure paths discard rather than lose; recycle on empty deck via `rng`. `_M1_EFFECT_CARD` removed. 9 new tests in `test_round_flow.py`. |
| RUL-48 | #42 | Single-line `cards-inventory.md` fix: `noun.hits` row now cites `player.history.hits_taken_this_game`. |
| RUL-50 | #43 | `design/state.md` Phase: resolve steps 5/6 swapped (step 5 = WHEN trigger; step 6 = JOKER attachment). ECHO described as one-shot WHEN promotion with conditional re-fire. |

**Lessons captured** (`docs/workflow_lessons.md`):
- 2026-05-10: revealed_effect pin fan-out — every Phase 3 PR needed pin; CLEAN merge mechanics didn't catch
- 2026-05-10: deck-size fragility in test helpers — seed-0 lucky deals invisibly bake into 14+ tests
- 2026-05-10: behavioural-substrate cascade at depth (RUL-47/RUL-54) — `rng=None` fallback didn't bite until round 13, escaping diff-level PR review. Proposes a third "conditional-substrate" axis alongside code-substrate and behavioural-substrate.

M2 Phase 2 SHIPPED (RUL-31 cards/state.py substrate, RUL-32 WHEN+WHILE lifecycle, RUL-33 GENEROUS+CURSED labels). M1.5 smoke re-contract SHIPPED (RUL-34). M2 Phase 3 fan + Wave 1 + Wave 2 + RUL-54 substrate fix SHIPPED (14 PRs in this stretch, all green).

## Open judgment calls

- **Canonical legality module**: `bots.random.enumerate_legal_actions` is the de-facto canonical surface (RUL-52, exercised by `bots/human`). M4 ISMCTS rollouts will consume it; the M3 WS protocol's `action-submit` envelope will likely want a canonical action shape that lives outside `bots/random`. Promote to `legality.py` when M3 starts? Open.
- **Foundation Client substrate spike scope**: M3 substrate-first entry per ADR-0006 is "WebSocket protocol shape spike + ratification ADR". Does the spike output live as one ADR (protocol-envelope shape) or two (envelope shape + state-broadcast cadence)? Defer to the spike worker's hand-back.
- **M2 watchable smoke headroom**: 6/10 floor with one cap-hit of slack (5 winners would breach). Tight but defensible — RUL-55's earlier 7/10 floor was an artifact of half-wired vocabulary (MARKED + CHAINED-clear absent in production; SHOP empty). The post-M2.5 6/10 floor is the honest random-bot ceiling against the full M2 ruleset. Per ADR-0006 the next gate is M3 Foundation Client (human playtest signal) then M4 ISMCTS (smart bot retune). Smoke regression headroom won't grow until M4.
- **Deck-composition fragility extends beyond `_drive_to_first_build`** (RUL-55 Lever B finding, RUL-61 confirmed): the same fragility hit `effect_cards:` — adding 2 cards lifted deck depth 12 → 14, shifted recycle timing past round 13, dropped the watchable floor 7/10 → 6/10 (one seed flipped). Any future ticket that changes `cards.yaml deck:` OR `cards.yaml effect_cards:` composition must rebase + run `test_cards_loader.py`, `test_jokers.test_full_game_round_trip_with_persistent_when_joker`, `test_determinism.test_recycle_path` before merge — and expect a watchable-smoke re-baseline.

## Phase 3 prep — why RUL-34 landed first

RUL-31's worker probe found that even silently-safe deck additions (ANYONE/EACH no-op via empty scope; JOKERs sit in-hand) regress the M1.5 watchable smoke 6/10 → 1-2/10 winners by diluting the rule-fire pool. Each Phase 3 ticket extends `cards.yaml deck:` for its consumer, so the smoke would have gone red on the first Phase 3 PR even when the PR is correct.

**RUL-34** re-contracted the M1.5 smoke as a regression detector during Phase 3: dropped `_MIN_WINNERS` to 0; widened `_MIN_RUNS_WITH_RESOLVE` to 7 and `_MIN_TOTAL_RESOLVES` to 34 (worst-case × 0.7); deleted `test_at_least_one_seed_produces_a_winner`. The "real watchable bar" moves to **RUL-35** (M2 watchable smoke), which lands as the Wave 3 gate and reclaims winner emergence on the fully-wired M2 deck.

## M2 Phase 2 Done summary

3 sub-issues closed:
- **RUL-31** — state.py additive (`CardType.EFFECT`, `Card.scope_mode`, `GoalCard`); cards.yaml extended with full M2 vocabulary; cards.py loader covers new sections + `load_effect_cards` / `load_goal_cards` helpers.
- **RUL-32** — `persistence.tick_while_rules` and `persistence.check_when_triggers`. WHILE persists; WHEN FIFO + discard-on-fire; depth-3 recursion cap; dormant-label handling. Phase 3 effect dispatcher replaced the Phase 2 stub.
- **RUL-33** — GENEROUS = argmax(`history.cards_given_this_game`); CURSED = argmax(`status.burn`). ADR-0001 tie-break: ties → all; zero → empty. MARKED/CHAINED stay empty pending status-apply ticket.

## Done (chronological, this session)

M1 + M1.5 + M2 Phase 1 + M2 Phase 2 + M2 Phase 3 fan + Wave 1 + Wave 2 + Wave 3 (RUL-35) + Wave 4 (RUL-51 + RUL-53 + RUL-55) = ~37 tickets shipped. **M1, M1.5, and M2 all closed.** Next milestone: M3 ISMCTS (RUL-NN to be opened).

## Locked decisions / substrate watchpoints

- `engine/src/rulso/state.py` is the contract. **Additive-only edits.**
- Pydantic v2 + frozen by default; tuples for collections.
- M2 stubs are fully replaced — SHOP entry landed via RUL-51 (PR #55).
- Pre-commit hook resolves `ruff` via `uv run --project engine`.
- **Active ADRs**: ADR-0001 (floating-label definitions), ADR-0002 (comparator dice flow), ADR-0003 (SUBJECT.scope_mode enum), ADR-0004 (operator MODIFIER attachment), ADR-0005 (GoalCard typing), ADR-0006 (M3/M4 reorder — Foundation Client first), ADR-0007 (SHOP payload semantics), ADR-0008 (WS protocol envelope shape).
- Workers do not edit `docs/<area>/readme.md` — orchestrator owns the index, batched into RUL-23 commits per merge sweep.
- Workers branch worktrees from `origin/main` (not local HEAD) — `git fetch origin && git worktree add ... origin/main`.
- All orchestrator-authored cross-cutting commits route through `RUL-23:`.
- Cross-reference identifier names when merging spike/data PRs — grep the engine for downstream consumers.
- Card naming convention (M1.5-ratified, M2-extended): SUBJECT names use `Player.id` literals (`p0..p3`) and `labels.LABEL_NAMES` keys (`"THE LEADER"`); effect-card IDs follow `eff.<status>.<verb>.[N]`.
- **Substrate-and-data tickets** must split DoD into (a) data loadable + (b) data observable in runtime.
- **Behavioural-substrate cascade rule** (2026-05-10): when a PR changes a public-function contract (signature, required-field consumption, exception class), every test that constructs `GameState` for the affected code path is implicitly impacted. Rebase against post-merge main and run affected tests before squash-merge if the PR is part of a parallel fan with a sibling that landed a contract change. CLEAN merge mechanics is necessary but not sufficient.
- **Conditional-substrate rule** (2026-05-10, RUL-54): when a PR adds a code path that fires conditionally on accumulated runtime state (deck exhaustion, retry counter, history growth), spot-check by asking "what's the depth at which this branch first triggers, and does any test reach it?" If no test reaches the branch and it's reachable in production, the path is unreviewed substrate. RUL-47's `rng=None` fallback at the recycle site didn't bite until round 13; RUL-54 lifted it to a `ValueError` so future callers can't silently regress. Disjoint-stream pattern: `rng = seed`, `refill_rng = seed ^ 0x5EED`, `dice_rng = seed ^ 0xD1CE`, `effect_rng = seed ^ 0xEFFC` (RUL-54).
- **Engine action surface (post-RUL-65, 2026-05-11)**: `engine/src/rulso/legality.py` is the canonical home for action shapes (`PlayCard` / `DiscardRedraw` / `Pass` / `PlayJoker` / `Action` discriminated union) **and** `enumerate_legal_actions(state, player)`. Internal `_enumerate_plays` / `_enumerate_discards` co-located there to dodge a `bots.random ↔ legality` import cycle. `bots.random` keeps `choose_action` (PLAY_BIAS-weighted picker, `PLAY_BIAS = 0.75` post-RUL-55), `select_purchase` (SHOP), `_find_player`. `protocol.py`'s `ClientAction` discriminated union and the bot's constructor calls share the same Pydantic class identity (single source = `legality`), preserving ADR-0008's "no drift" guarantee. `bots/human.py` and `server.py` both validate against `legality.enumerate_legal_actions`.
- **SHOP substrate (Wave 4, RUL-51)**: `Phase.SHOP` real handler at `engine/src/rulso/rules.py` (`enter_round_start` step-5 cadence check + `complete_shop` / `apply_shop_purchase` / `shop_purchase_order` helpers). `ShopOffer` model + `shop_pool` / `shop_offer` / `shop_discard` fields on `GameState`. Cadence `round_number % SHOP_INTERVAL == 0` (every 3 rounds); buy order `(vp asc, chips asc, seat asc)` per `design/state.md`. `cards.yaml shop_cards:` ships empty — SHOP short-circuits when no offers; content lands via RUL-56.

## Conventions (also in CLAUDE.md, restated for reflex)

- Linear ticket prefix `RUL-`; team `Rulso`; projects mirror areas.
- Branch: `RUL-<id>-<slug>`. Worktree: `.worktrees/RUL-<id>-<slug>` (gitignored).
- Commit prefix: `RUL-<id>: <imperative subject>`. Orchestrator meta commits use `RUL-23:`.
- Status flow: Backlog → Todo → In Progress → In Review → Done.
- PRs are checkpoints. Squash-merge on clean; rebase-then-squash on conflict. **Spot-check one DoD bullet against the diff before merging.**
- Hand-over template (per global `~/Documents/Projects/CLAUDE.md`): first line `=== TICKET-ID — title ===`; closing `=== END ===`.

## Bootstrap incantation

```
Act as orchestrator for Rulso. Read CLAUDE.md (auto-loaded), STATUS.md, and the
last 5 entries of docs/workflow_lessons.md if present. Then await instructions.
```

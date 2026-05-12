_Last edited: 2026-05-10 by RUL-29_

# Rulso — Effect-Card Inventory

The effect-card vocabulary the M2 engine consumes when an IF rule resolves. This document is the design contract; `engine/src/rulso/effects.py` realises a subset.

This file defines:
- the **effect-card schema** (fields read by the M2 effect dispatcher)
- the **M2 starter subset** (~12 effect cards) and the engine fields each mutates
- the **revealed-effect lifecycle** (draw → apply → discard) per `design/state.md`
- the **`_apply_stub_effect` → `_apply_revealed_effect` migration** plan for `engine/src/rulso/effects.py`
- naming coordination with **RUL-30** (status-token application sources)

It does **not** define per-effect chip prices, dice-driven effect magnitudes, JOKER-modified effects, or composite (chained) effect cards. Those are flagged as out of scope at the bottom.

---

## What an effect card *is*

Each round (`design/state.md` → `Phase: round_start`, step 6) the engine reveals one card from `effect_deck` face-up alongside the active rule area; it lands on `GameState.revealed_effect: Card | None` (added by RUL-8). When the round's IF rule resolves (`Phase: resolve`, step 4) the revealed effect is the **outcome** applied to every player matched by the rule's IF clause.

> **Rule = WHO matches. Effect card = WHAT happens.**
>
> The rule (`[CONDITION] [SUBJECT] HAS [QUANT] [NOUN]`) selects the scoped players and filters down to matches. The revealed effect card determines the mutation applied to those matches. They are intentionally orthogonal so the same rule can have radically different consequences round-to-round.

This separation is why M1.5's `_apply_stub_effect` ignores `revealed_effect` and hardcodes `+1 VP` — there is no effect-card vocabulary yet. M2 wires the dispatcher.

---

## Effect-card schema

Each effect card is a `Card` (per `engine/src/rulso/state.py`) with:

| Field | Type | Read by | Notes |
|---|---|---|---|
| `id` | `str` | pile management, telemetry | Convention: `eff.<kind>.<form>[.N]` (e.g. `eff.chips.gain.5`). Never user-visible. |
| `type` | `CardType.EFFECT` | dispatcher (rejection of non-effects) | Requires a new `CardType` enum value (additive — see "Substrate notes" below). |
| `name` | `str` | dispatcher → effect-kind handler | Render-token; uppercase; colon-separated parameters. Format: `<KIND_TOKEN>[:<MAG>]`. |

The dispatcher reads `name` only — `id` exists for pile management. This mirrors the convention ratified in `design/cards-inventory.md`.

### Implicit fields parsed from `name`

The `name` token encodes three logical fields the dispatcher derives at apply-time:

| Logical field | Source | Values |
|---|---|---|
| `effect_kind` | `name` prefix before `:` | `chips_grant` / `chips_drain` / `vp_grant` / `vp_drain` / `status_apply` / `status_clear` / `hand_size_modify` / `noop` |
| `magnitude` | `name` integer suffix after `:` (default `1` if omitted) | `int`. Always non-negative; `_drain` and the `-modify` discard variant carry sign in the kind, not the magnitude. |
| `target_modifier` | inferred from kind for the M2 starter; explicitly encoded only when it diverges from `all_matched` (see below) | `all_matched` / `active_seat_only` / `everyone_except_matched` / `dealer_only` |

**Why parse the kind from `name` rather than store it as a model field?** Mirrors how QUANT cards encode `OP:N` (per `cards-inventory.md`): keeps the `Card` shape uniform across categories, keeps `cards.yaml` declarative, defers per-card-shape divergence until it pays for itself. If M2 implementation finds the parse-on-every-resolve cost meaningful (it won't — pre-parse at deck-build time is one line), an `EffectCard` Pydantic submodel can be introduced additively.

### `target_modifier` semantics

The default for every M2 starter card is **`all_matched`** — the effect applies once per player satisfying the IF clause. Other modifiers are listed for completeness; only one M2 starter card uses a non-default modifier (`APPLY_BLESSED` → `everyone_except_matched`, see below).

| Modifier | Meaning | Notes |
|---|---|---|
| `all_matched` | Apply once per player in the match-set returned by `_evaluate_has`. | Default. Matches today's `_apply_stub_effect` semantics. |
| `active_seat_only` | Apply to the player who finalised the rule (last play in `RuleBuilder.plays`), regardless of match-set. | M2; useful for SHOP-flavoured rewards. |
| `everyone_except_matched` | Apply to `state.players \ match_set`. | M2; the "punish-the-mob, reward-the-rest" axis. |
| `dealer_only` | Apply to `state.players[state.dealer_seat]`. | M2; rare; supports "house edge" effect cards. |

For the M2 starter, encoding rule: cards whose modifier is `all_matched` carry no modifier marker in `name` (e.g. `GAIN_CHIPS:5`); cards with a non-default modifier carry the suffix `@<MOD>` (e.g. `APPLY_BLESSED@EXCEPT_MATCHED`). One precedent card (`APPLY_BLESSED`) below; expansion deferred.

### Status-apply / status-clear sub-schema

Boolean statuses (`mute`, `blessed`, `marked`, `chained`) take `magnitude=1` (apply) or `magnitude=0` (no-op; not minted). Counter status `burn` takes `magnitude=N` (tokens added). The status name is embedded in the `name` token (e.g. `APPLY_BURN:1`, `APPLY_MUTE`, `CLEAR_BURN:1`), and the dispatcher derives the `Player.status` field name from it.

**Coordination with RUL-30.** RUL-30's `design/status-tokens.md` is the source of truth for *which* status keys exist and their canonical render-tokens. This document assumes the keys match `engine/src/rulso/state.py:PlayerStatus` (`burn`, `mute`, `blessed`, `marked`, `chained`) and uses uppercase render-tokens accordingly. **If RUL-30 lands a different keying or different uppercase tokens, this document yields to RUL-30** — the dispatcher's status-name parser is one regex line and trivial to reconcile. The engine ticket that wires `_apply_revealed_effect` MUST cross-reference both spikes before locking the parser.

---

## M2 starter subset (12 cards)

Each pick justified by **what it tests in the dispatcher pipeline**. Together they exercise every `effect_kind` and every M2-starter-relevant `Player` / `GameState` mutation path.

| id | name | effect_kind | magnitude | target_modifier | Mutates | Tests |
|---|---|---|---|---|---|---|
| `eff.chips.gain.5` | `GAIN_CHIPS:5` | `chips_grant` | 5 | `all_matched` | `Player.chips` | small chip reward; common positive outcome |
| `eff.chips.gain.10` | `GAIN_CHIPS:10` | `chips_grant` | 10 | `all_matched` | `Player.chips` | larger reward; magnitude-driven dispatch (proves magnitude isn't ignored) |
| `eff.chips.drain.5` | `LOSE_CHIPS:5` | `chips_drain` | 5 | `all_matched` | `Player.chips` | symmetric drain; floors at 0 (per `state.md` "Player at 0 chips: still plays") |
| `eff.vp.gain.1` | `GAIN_VP:1` | `vp_grant` | 1 | `all_matched` | `Player.vp` | replaces the M1.5 stub; preserves end-condition reachability via the same mutation path |
| `eff.vp.drain.1` | `LOSE_VP:1` | `vp_drain` | 1 | `all_matched` | `Player.vp` | VP can decrease; floors at 0 (no negative VP) |
| `eff.burn.apply.1` | `APPLY_BURN:1` | `status_apply` | 1 | `all_matched` | `Player.status.burn` (int +=) | counter-status path; cumulative; ticks at next `round_start` step 2 |
| `eff.mute.apply` | `APPLY_MUTE` | `status_apply` | 1 | `all_matched` | `Player.status.mute = True` | boolean-status path; cleared end-of-next-round (per `state.md`) |
| `eff.blessed.apply` | `APPLY_BLESSED@EXCEPT_MATCHED` | `status_apply` | 1 | `everyone_except_matched` | `Player.status.blessed = True` | non-default `target_modifier`; proves modifier dispatch is wired |
| `eff.chained.apply` | `APPLY_CHAINED` | `status_apply` | 1 | `all_matched` | `Player.status.chained = True` | persistent boolean (cleared only by removal); proves lifetime semantics carry through |
| `eff.burn.clear.1` | `CLEAR_BURN:1` | `status_clear` | 1 | `all_matched` | `Player.status.burn` (int -=, floor 0) | clear-path counterpart; magnitude on clear differs from apply (decrement, not assignment) |
| `eff.draw.2` | `DRAW:2` | `hand_size_modify` | 2 | `all_matched` | `Player.hand` (+= 2 from `state.deck`) | hand mutation; reuses the M1 deck-draw helper used at `Phase: resolve` step 12 |
| `eff.draw.2.alt` | `DRAW:2` | `hand_size_modify` | 2 | `all_matched` | `Player.hand` (+= 2 from `state.deck`) | RUL-73 replacement for the original `eff.noop` sentinel; doubles the DRAW:2 frequency so reveal-day still feels like something happens to SUBJECT |

**14 cards because**: 5 effect_kind families (chips, vp, status_apply, status_clear, hand_size_modify) × 1-3 cards each + the MARKED applier + the CHAINED clearer (RUL-61) + the second DRAW:2 (RUL-73 replacing the deliberate-NOOP sentinel). The `NOOP` dispatcher path is still exercised through `effects.py:_noop` whenever `revealed_effect` is `None` (deck-empty fallback at `round_start` step 6) — no `eff.noop` card is needed for that coverage. Smaller than 12 leaves a kind family untested; larger duplicates dispatch paths with different magnitudes (a parametrisation concern, not a vocabulary one). MARKED status is intentionally excluded from the starter — it interacts with `EACH PLAYER` SUBJECT scope, which is itself M2-late (per `cards-inventory.md`); coupling them is needless risk for the head fan.

---

## Revealed-effect lifecycle

The full cradle-to-grave path of a single effect card, anchored to `design/state.md`:

```
round_start step 6:  effect_deck.pop() → revealed_effect
                     (face-up; visible to all; bots include in heuristic)

build phase:         revealed_effect is read-only (planning input);
                     no mutation regardless of slot fills

resolve step 4:      _apply_revealed_effect(state, matching_ids)
                     ↳ dispatch on effect_kind
                     ↳ apply magnitude × target_modifier to Player(s)

resolve step 10:     effect_discard += (revealed_effect,)
                     revealed_effect = None
                     (cleanup; mirrors the fragment-discard step)
```

### Deck-empty reshuffle

`design/state.md` "Edge Case Index" specifies: "Empty deck: reshuffle discard into deck." Applies to `effect_deck` symmetrically. At `round_start` step 6, if `effect_deck == ()`, shuffle `effect_discard` into `effect_deck` first; if both are empty (only possible if every effect card is currently in `revealed_effect` slots across the table, which can't happen because there is exactly one per round), `revealed_effect` stays `None` and `_apply_revealed_effect` is a no-op (same path the `NOOP` card exercises).

### Rule-failure interaction (decided: **discard**)

`design/state.md` `Phase: build` says: "If any required slot unfilled → rule **fails**: discard fragments, no effects, no goal claims, dealer rotates, transition → `round_start`."

**Decision: the revealed effect ALSO discards on rule failure.** Reasons:

1. **Symmetry with fragment discard.** Failure tears down the round's structures uniformly; carrying state across a failed round violates the "fresh round" mental model.
2. **Avoids two-headed reveals.** `round_start` step 6 unconditionally reveals from `effect_deck`. If the prior effect hadn't discarded, the engine would either (a) overwrite it silently (data-loss surprise) or (b) accumulate (`Tuple[Card, ...]` revealed effects, unspecified semantics).
3. **Skipped-effect tax aligns with skipped-rule tax.** Both halves of the round die together. Carrying an effect to next round would reward failure with a "free pre-revealed effect" — design-counterproductive.
4. **Cheap to implement.** The cleanup hook lives in the failure path next to fragment discard; ~3 lines.

Resolver-side sequence on failure:
```
build phase end (slot unfilled):
    state.discard += rule_fragments (existing)
    state.effect_discard += (state.revealed_effect,) if state.revealed_effect else ()
    state.revealed_effect = None
    rotate dealer
    transition → round_start
```

The next `round_start` step 6 then reveals a fresh effect, identically to the post-resolve path. `state.md` may want a one-line clarification at the failure step; the engine ticket that lands rule-failure cleanup should append it (or a docs ticket can pre-fix it before the engine work — orchestrator's call).

---

## `_apply_stub_effect` → `_apply_revealed_effect` migration

Today (M1.5), `engine/src/rulso/effects.py:_apply_stub_effect` ignores `state.revealed_effect` entirely and hardcodes `+_STUB_VP_GAIN` (`= 1`) VP for every matched player. M2 swaps this for a real dispatcher.

### Replacement shape (sketch — engine ticket owns the final form)

```python
# engine/src/rulso/effects.py (M2)

EffectKind = Literal[
    "chips_grant", "chips_drain",
    "vp_grant", "vp_drain",
    "status_apply", "status_clear",
    "hand_size_modify",
    "noop",
]

@dataclass(frozen=True)
class _ParsedEffect:
    kind: EffectKind
    magnitude: int
    status_field: str | None  # only for status_apply / status_clear
    target_modifier: str       # default "all_matched"

def _parse_effect_name(name: str) -> _ParsedEffect: ...

def _resolve_targets(
    state: GameState,
    matching_ids: frozenset[str],
    target_modifier: str,
) -> frozenset[str]: ...

_EFFECT_HANDLERS: dict[EffectKind, Callable[[GameState, frozenset[str], _ParsedEffect], GameState]] = {
    "chips_grant":      _apply_chips_delta,        # +magnitude
    "chips_drain":      _apply_chips_delta_negative,  # -magnitude, floor 0
    "vp_grant":         _apply_vp_delta,           # +magnitude
    "vp_drain":         _apply_vp_delta_negative,  # -magnitude, floor 0
    "status_apply":     _apply_status,             # bool=True / burn += magnitude
    "status_clear":     _clear_status,             # bool=False / burn -= magnitude (floor 0)
    "hand_size_modify": _adjust_hand,              # draws magnitude cards from state.deck
    "noop":             lambda s, _t, _e: s,
}

def _apply_revealed_effect(
    state: GameState,
    matching_ids: frozenset[str],
) -> GameState:
    effect = state.revealed_effect
    if effect is None:
        return state
    parsed = _parse_effect_name(effect.name)
    targets = _resolve_targets(state, matching_ids, parsed.target_modifier)
    return _EFFECT_HANDLERS[parsed.kind](state, targets, parsed)
```

**Call site**: `resolve_if_rule` swaps its terminal `return _apply_stub_effect(state, matching)` for `return _apply_revealed_effect(state, matching)`. The `_NOUN_RESOURCES` / `_evaluate_has` / `_compare` / `_parse_quant` helpers and the `_scope_subject` label-aware path are **unchanged** — the migration is strictly the post-match application step.

**`_STUB_VP_GAIN` removal**: the `+1 VP` hardcoded constant becomes the `vp_grant` magnitude on the `eff.vp.gain.1` card, applied through `_apply_vp_delta`. The constant deletes; the test that asserted it should pivot to assert the dispatch path lands the same mutation when `revealed_effect` is `eff.vp.gain.1`.

**Discard hook**: `_apply_revealed_effect` does NOT itself discard the effect card. The discard happens at `Phase: resolve` step 10 (cleanup) — same place fragment cleanup lives — driven by `engine/src/rulso/rules.py` (which owns the resolve-step orchestration). Keeps the dispatcher pure (`state in → state out`) and centralises lifetime mutations in the rules module. The engine ticket wiring `_apply_revealed_effect` should add the cleanup line at the same time.

### Substrate notes for the engine ticket

These are NOT implemented in this spike — flagged for the M2 substrate ticket (RUL-26 or successor):

1. **`CardType.EFFECT` enum value** must be added to `engine/src/rulso/state.py:CardType`. Additive; no rename / retype. Existing card categories unaffected.
2. **`effect_deck` seeding**: `cards.yaml` (RUL-17) currently seeds `deck` only; the loader needs an `effect_cards:` section and the engine setup needs to populate `GameState.effect_deck` from it. Mirrors the existing `cards.yaml` → deck flow.
3. **`PlayerStatus.burn -= magnitude`** semantics: today `PlayerStatus` is frozen Pydantic with `burn: int = 0`. The `_clear_status` handler needs to floor at 0 (`max(0, burn - magnitude)`). Ditto `chips_drain` / `vp_drain`. No new field; just disciplined arithmetic in the handler.

---

## Status-applying effects (matrix for RUL-30 cross-reference)

Five status keys live on `Player.status` (per `engine/src/rulso/state.py:PlayerStatus`). The M2 starter applies four of them; one (MARKED) is intentionally deferred.

| Status key | Type | Apply card | Clear card | Lifetime (per `state.md`) | M2 starter? |
|---|---|---|---|---|---|
| `burn` | `int` (counter) | `eff.burn.apply.1` (`APPLY_BURN:1`) | `eff.burn.clear.1` (`CLEAR_BURN:1`) | persists; ticks `BURN_TICK` chips/round at `round_start` step 2; cleared by removal cards | **yes** (apply + clear) |
| `mute` | `bool` | `eff.mute.apply` (`APPLY_MUTE`) | (auto-clears end-of-round; no card) | cleared at end of the round it applied | **yes** (apply only) |
| `blessed` | `bool` | `eff.blessed.apply` (`APPLY_BLESSED@EXCEPT_MATCHED`) | (auto-clears on next chip-loss) | cleared on use | **yes** (apply only) |
| `marked` | `bool` | (deferred — depends on `EACH PLAYER` scope) | (auto-clears end of `resolve`) | cleared at end of `resolve` | **no** |
| `chained` | `bool` | `eff.chained.apply` (`APPLY_CHAINED`) | (no auto-clear; removal card only) | cleared by removal cards only | **yes** (apply only) |

**RUL-30 dependency**: status-token render-tokens, application sources, and the interaction matrix between status types live in `design/status-tokens.md` (RUL-30 output). Where this document and RUL-30 disagree on naming, **RUL-30 wins** for status-key names and apply/clear render-tokens; this document yields and the engine ticket reconciles. The fields in `PlayerStatus` are the binding shared substrate — both spikes reference them by Python attribute name to keep coordination loss-less.

---

## Effect cards vs rule effects (worth restating)

A rule (built during `Phase: build`) has shape `[CONDITION] [SUBJECT] HAS [QUANT] [NOUN]`. It does NOT carry an effect — it only **scopes who matches**. The revealed effect card is what happens to those matches.

| Rule clause | Question it answers | Reads |
|---|---|---|
| `CONDITION` | What lifetime? | Template card (IF / WHEN / WHILE) |
| `SUBJECT` | Which players are in scope? | `Player.id` / labels |
| `HAS [QUANT] [NOUN]` | Of those, which actually match? | `Player.chips` / `Player.vp` / etc. |
| (revealed effect, separate card) | What happens to the matches? | `effect_kind` + `magnitude` + `target_modifier` |

This separation enables effect variability — the same rule template ("THE LEADER HAS LESS THAN 5 CHIPS") gains entirely different feel round-to-round depending on whether the revealed effect is `GAIN_CHIPS:10` (relief) or `APPLY_BURN:1` (kicking them while they're down). Designing rules and effects as orthogonal axes is intentional.

A common confusion this fends off: a player playing a NOUN like `CHIPS` is sometimes mentally read as "lose chips" / "gain chips". It does not. The NOUN is **only the read property** for the IF clause. The chip mutation comes from the revealed effect, never from the rule.

---

## Out of scope (flagged for future tickets)

These are explicitly NOT covered by this inventory or the M2 starter; future tickets will address them:

1. **WHILE re-fire interactions with `revealed_effect`.** WHILE rules tick at `round_start` step 4, **before** the round's effect reveal at step 6. So the WHILE-tick uses last round's discarded effect (i.e., none) — which is operationally fine but means WHILE rules effectively have no effect-card outcome on their tick, only on the round they were initially built. This is probably wrong long-term; needs an ADR before WHILE rules become common. Either (a) WHILE-tick uses the *currently revealed* effect from the round being torn down (off-by-one model), (b) WHILE-tick has its own per-rule frozen effect baked at build time, or (c) WHILE rules have no effect-card semantic and apply a default outcome. Spike ticket; out of scope here.

2. **JOKER-modified effects.** Cards like `JOKER:DOUBLE` (per `cards-inventory.md`) could plausibly double the effect-card magnitude, double the target set, or double the resolve cycle. Decision belongs with the JOKER spike, not here.

3. **Chained / composite effect cards.** Cards encoding multiple effects ("GAIN 5 CHIPS, then LOSE 1 VP" or "EACH MATCHED PLAYER → BURN 1; EACH UNMATCHED → BLESSED") would need `name` to encode an ordered list. Defer to a post-M2 expansion ticket; the M2 dispatcher should be straightforward enough to extend additively.

4. **Dice-driven effect magnitude.** Mirrors the comparator dice tension flagged in `cards-inventory.md`. M2 starter bakes magnitude into the card; if effect cards later draw dice at apply-time, the parser extends without breaking the baked variants.

5. **Per-card chip prices for the SHOP.** Effect cards are not currently sold at the SHOP (`shop_deck` is its own deck per `state.md` `Phase: shop`). If they ever are, prices live with shop config, not here.

6. **Effect-card art / sprite mapping.** Aesthetic concern; deferred to client work.

7. **Telemetry of effect resolution.** Replay tooling will want to log `(rule, revealed_effect, match_set, mutations)` per round; the dispatcher's pure-function shape supports it trivially, but the logging hook design lives elsewhere.

8. **MARKED status apply card.** Deferred from the starter pending `EACH PLAYER` SUBJECT scope (M2-late per `cards-inventory.md`). Add when MARKED's interaction with `EACH PLAYER` is locked.

---

## Items intentionally deferred from this inventory

- Concrete `effect_cards:` YAML schema (the `cards.yaml` extension). The engine ticket that wires `_apply_revealed_effect` will land it alongside the loader extension.
- Per-effect chip prices (no SHOP integration in M2).
- Render rules / iconography for effect cards. Aesthetic work, not contract work.
- Bot heuristics for incorporating `revealed_effect` into card-play decisions. Bot work, not effect-vocabulary work.

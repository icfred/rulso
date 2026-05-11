# ADR-0007 — SHOP payload semantics: card-buy via existing `CardType` variants

**Status**: Accepted (2026-05-11)

## Context

RUL-51 shipped the SHOP cadence + ordering substrate. `Phase.SHOP` fires every `SHOP_INTERVAL = 3` rounds, draws up to 4 face-up offers, iterates buyers in ascending-VP order, deducts chips, and appends the wrapped card to the buyer's hand. The substrate is exercised by 13 tests in `engine/tests/test_shop.py`; nothing on `main` lights it up in normal play because `design/cards.yaml shop_cards:` is empty.

RUL-56 is filed to populate the content. It blocks on this ADR — the existing substrate already constrains the payload shape (see "Substrate state" below), and three candidate semantics surfaced in design conversation deserve a written lock before content lands:

1. **Status-clear payloads** — buy → clear specific status tokens on the buyer (e.g. "5 chips → clear all BURN"). Shop-as-catch-up framing: lowest-VP buys first, so the most-burned player gets relief.
2. **Card-buy payloads** — buy → append a fragment to the buyer's hand (SUBJECT / NOUN / MODIFIER / JOKER). Shop-as-deck-shaping framing: the buyer steers the rule-grammar pool toward their strategy.
3. **Effect-card payloads** — buy → schedule a one-shot effect that resolves on the buyer's next BUILD turn. Shop-as-tactical-reserve framing.

These can also combine. The ADR locks one shape for M2.5; expansions are additive and follow.

### Substrate state (already-merged on `main`)

`engine/src/rulso/cards.py:117` defines `_ShopEntry`:

```python
class _ShopEntry(BaseModel):
    id: str
    name: str
    price: int = Field(ge=0)
    payload_type: CardType
```

`load_shop_offers()` constructs each offer as `ShopOffer(card=Card(id, name, type=payload_type), price=price)`. `apply_shop_purchase()` (`rules.py:253`) deducts chips and appends `offer.card` to `Player.hand`. The substrate **already commits to shape 2** — `payload_type` is restricted to `CardType` (SUBJECT / NOUN / MODIFIER / JOKER / EFFECT), and the purchased value is a `Card` that lives in `Player.hand` from then on.

Shapes 1 and 3 are **not wired**. Either would require additive substrate:
- Shape 1: a dispatch hook at purchase-apply time that consumes the offer's payload and mutates `Player.status` directly (no card lands in hand). Either a new `_ShopEntry.effect` field or a sentinel `CardType.SHOP_ACTION` variant with bespoke `apply_shop_purchase` branching.
- Shape 3: a new `GameState` field (e.g. `pending_shop_effects: tuple[ShopEffect, ...]`) consumed at the buyer's next BUILD step, plus a new payload shape disjoint from `Card`. The existing main-deck legality checks reject anything that doesn't fit `CardType`.

## Decision

**Lock shape 2: SHOP payloads are `Card` instances delivered to `Player.hand` via the existing `_ShopEntry.payload_type` route.** Purchased cards behave identically to main-deck cards from the moment they enter the hand — same legality, same MUTE / status-token interaction, same discard semantics, same JOKER-attachment path.

Rationale:

- **Path of least resistance.** RUL-51's substrate already implements this. RUL-56 ships as pure `design/cards.yaml` data (zero engine code change).
- **RUL-56 hard constraint matches.** RUL-56 names (a) — "reuse existing CardType.SUBJECT/NOUN/MODIFIER/JOKER and behave like any other card once in hand" — as the default; (b) "introduce a new CardType.SHOP_* variant with bespoke legality" is only invoked if playtest signal demands. No playtest signal exists yet.
- **No vocabulary collision.** Shape 1 (status-clear) duplicates the existing effect-card route: `eff.burn.clear.1` (`CLEAR_BURN:1`) already exists in `design/cards.yaml effect_cards:` and the dispatcher applies it to matched players each round. Inventing a SHOP-side `clear-burn` payload reinvents the same mechanic with a different trigger surface.
- **Strategic shape fits the design intent.** "Lowest-VP buys first" is a catch-up signal, but catch-up via *deck-shaping* is meaningful when the M2 deck is wide and seed-driven: a wounded player can buy a clutch SUBJECT or comparator that the random shuffle hasn't dealt them. Shape 2 surfaces a *real* strategic decision per shop round; shape 1 ("clear N BURN") collapses to "buy the cheapest BURN-clear you can afford" the moment BURN is on you.
- **Forward compatibility.** Shapes 1 and 3 are additive future tickets if M3 playtest signal demands them. This ADR locks shape 2 as the default, not the only-possible. A future ADR can extend SHOP with a status-clear hook or a pending-effect queue without rewriting `_ShopEntry` — both would be new fields / new sentinel types alongside the existing route.

### M2.5 SHOP starter subset (7 offers)

Sized at 7 — slightly above the 4-per-round draw size so the pool sustains across the first two SHOP rounds (rounds 3 and 6) before the recycle path fires. Every offer's `name` matches an identifier the engine already consumes (`labels.LABEL_NAMES`, `rules._OP_ONLY_COMPARATOR_NAMES`, `rules._JOKER_VARIANTS`), so no engine path needs widening.

| id | name | payload_type | price | Why this card |
|---|---|---|---|---|
| `shop.subj.wounded` | `THE WOUNDED` | SUBJECT | 5 | Wounded player targets themselves with a positive rule. Cheapest tier — accessible to a heavily-burned buyer. Matches `labels.WOUNDED`. |
| `shop.subj.leader` | `THE LEADER` | SUBJECT | 7 | Wounded player targets the leader with a punitive rule. Matches `labels.LEADER`. |
| `shop.mod.gt` | `GT` | MODIFIER | 6 | M2 OP-only comparator (ADR-0002 dice-driven). Rare main-deck slot (10/96); clutch buy when the rule needs a high threshold. |
| `shop.mod.eq` | `EQ` | MODIFIER | 6 | OP-only EQ — narrower hit, strategic value when paired with 1d6. Same rarity rationale as `GT`. |
| `shop.jkr.double` | `JOKER:DOUBLE` | JOKER | 10 | Doubles the round's revealed effect. High-impact tactical lever; matches `rules._JOKER_DOUBLE`. |
| `shop.jkr.echo` | `JOKER:ECHO` | JOKER | 9 | Re-fires the rule next round via WHEN promotion. Strategic continuity for catch-up. Matches `rules._JOKER_ECHO`. |
| `shop.jkr.persist_when` | `JOKER:PERSIST_WHEN` | JOKER | 12 | Promotes the rule to permanent WHEN-trigger. Premium tier; long-game lever. Matches `rules._JOKER_PERSIST_WHEN`. |

Composition: 2 SUBJECT, 2 MODIFIER, 3 JOKER. NOUN is intentionally absent — the main deck already carries 20 NOUN slots across 8 kinds; buying a NOUN offers little marginal value at M2's vocabulary depth.

Polymorphic SUBJECTs (`ANYONE` / `EACH_PLAYER`) are intentionally **excluded**. They require `scope_mode` to be threaded through `_ShopEntry`, which is an additive yaml schema change (one field on the model + one assignment in `load_shop_offers`). The change is small but takes M2.5 off the "data-only" path; defer until a future ticket that has reason to include polymorphic SHOP payloads.

### Pricing rationale

Anchor: 50 starting chips; SHOP fires round 3 first. A lagging player at round 3 typically holds 20–35 chips after BURN drains (5/token at `round_start` step 2) and discards (5 each). The price band 5–12 keeps every offer reachable from 12 chips up.

- **5–7 (cheap)**: single-play impact cards. `THE WOUNDED`, `THE LEADER`, `GT`, `EQ`. Strategic value lies in *availability*: the buyer chooses *which* SUBJECT or comparator to target rather than rolling the shuffle.
- **9–10 (mid)**: one-round high-impact JOKERs. `DOUBLE` and `ECHO` — both have visible immediate-round payoff (`DOUBLE` fires this round; `ECHO` next round).
- **12 (premium)**: persistent JOKERs. `PERSIST_WHEN` lodges the rule indefinitely; pricing reflects long-game value.

The price gradient (5 / 6 / 7 / 9 / 10 / 12) gives a real decision per shop round even when the draw lands on the cheap end — a 12-chip buyer with `PERSIST_WHEN` and `GT` both visible faces a meaningful tradeoff. RUL-56 may tune individual prices against M2 watchable-smoke winner-emergence data; the ADR fixes the *shape* and the *range*, not per-card specifics.

## Consequences

- **`design/cards.yaml shop_cards:`**: populated with 7 entries per the table above. Identifier prefix `shop.` keeps the namespace clean against the `subj.` / `mod.` / `jkr.` main-deck namespaces.
- **`engine/src/rulso/cards.py`**: no change. `_ShopEntry.payload_type` already restricts to `CardType`; the 7 starter entries all use SUBJECT / MODIFIER / JOKER.
- **`engine/src/rulso/rules.py`**: no change. `apply_shop_purchase` already appends `offer.card` to `Player.hand` correctly; once held, the card flows through `play_card` / `play_joker` / discard like any other.
- **`engine/src/rulso/state.py`**: no change. No new fields. The substrate-watchpoint additive-only rule is satisfied trivially (the watchpoint allows additive yaml; no schema change here).
- **`engine/src/rulso/bots/random.py`**: no change. `select_purchase` already implements "cheapest affordable, ties by lowest index". The heuristic remains valid against the 5–12 chip range — it will tend to buy `THE WOUNDED` / `GT` / `EQ` first when affordable, which is approximately correct catch-up behaviour.
- **M2 watchable-smoke baseline (`test_m2_watchable.py`, `docs/engine/m2-smoke.md`)**: SHOP now fires in CLI play once `shop_cards:` is populated. Winner counts and lifecycle floors may shift; RUL-56 is responsible for re-pinning the deterministic baseline. If winners drop below the existing floor, file a balance ticket — do not silently lower it (per RUL-56 hard constraint).
- **Determinism**: `start_game(seed)` already shuffles `shop_pool` from the same seeded rng; same seed in → same shop pool out. The seven-card pool with `_SHOP_OFFER_SIZE = 4` exercises both the happy path (offers available) and the recycle path (pool empties after round 9 once `shop_discard` is fed by unsold offers).
- **Cross-reference with effect-card vocabulary**: zero overlap. `eff.burn.clear.1` and `eff.mute.apply` keep their channel (random reveal each round); no SHOP card invokes `status_apply` or `status_clear` semantics. The two routes stay orthogonal.
- **Future-additive expansions**: shapes 1 and 3 remain available as future ADRs. Each would add (not replace) a route alongside this one — a new `_ShopEntry` variant or a new `GameState` field. The decision here does not close those doors.

## Alternatives considered

**(a) Status-clear payloads (shape 1).** Rejected. Duplicates `eff.burn.clear.1` and `eff.mute.apply` (existing in `effect_cards`); the effect dispatcher already applies status_clear to matched players each round. A SHOP-side BURN-clear would be a buy-it-when-you-need-it variant of the same mechanic — design-wise indistinguishable in playtest signal, but requires a new substrate hook (`_ShopEntry.effect` or a `CardType.SHOP_ACTION` sentinel) and a new branch in `apply_shop_purchase`. Cost > benefit at M2.5; revisit if M3 playtest data shows the effect-card random reveal is too unreliable for catch-up.

**(b) Effect-card payloads (shape 3).** Rejected. Requires a new `GameState` field (`pending_shop_effects` or equivalent) consumed at the buyer's next BUILD step, plus a payload shape disjoint from `Card`. The substrate cost is meaningful (state-machine extension, new test coverage, new persistence-tick interaction with WHILE rules). The strategic value is hard to evaluate without playtest signal — "tactical reserve" is a richer mechanic but also a steeper design surface. Defer to a post-M3 ticket if signal demands.

**(c) Combined shape — mix of card-buy + status-clear in the M2.5 starter.** Rejected. The combination requires shape 1's substrate hook *and* shape 2's content lane, doubling the M2.5 cost without doubling the playtest value. Picking one shape, exercising it across 7 offers, and learning from M3 playtest is the cheaper experiment.

**(d) Larger M2.5 starter (10+ offers).** Rejected. The 4-per-round draw size and the pool/discard recycle path means 7 offers already cover 2 full SHOP rounds before the recycle fires; expanding the pool delays the recycle code path without producing additional design signal. RUL-56 can grow the pool when playtest data justifies it.

**(e) Include polymorphic SUBJECTs (`ANYONE` / `EACH_PLAYER`) in the M2.5 starter.** Rejected for this ADR. Requires `scope_mode` to thread through `_ShopEntry` (additive but non-trivial). The starter intentionally stays on the data-only path; future tickets can widen the schema when there's reason to.

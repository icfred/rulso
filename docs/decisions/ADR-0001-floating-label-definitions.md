# ADR-0001 — Floating-label definitions and tie-break policy

**Status**: Accepted (2026-05-09)

## Context

`design/state.md:63-66` originally defined the floating labels as:

| Label | Definition | Tie-break |
|---|---|---|
| THE LEADER | argmax(chips) | ties → unassigned |
| THE WOUNDED | argmin(chips) | ties → unassigned |
| THE GENEROUS | argmax(cards_given_this_game) | ties → unassigned |
| THE CURSED | argmax(burn) | ties → unassigned |

When tickets RUL-19 (label computation) and RUL-16 (card-inventory spike) were authored, both adopted a different definition for `THE LEADER` (argmax of **vp** rather than chips) and a different tie-break rule (ties → **all tied players hold the label** rather than unassigned). The RUL-19 worker implemented per its ticket, flagged the divergence in the labels.py docstring + handback. RUL-16's inventory doc independently records the same updated definition.

The divergence wasn't an editing miss — both tickets state the new spec deliberately, with RUL-19's "Out of scope" calling out that "ties → all matching players" is the intended rule. Two design rationales:

- **VP, not chips, is the win condition**, so "the leader" by VP is the more meaningful semantic for rule-card scoping. Chip count is volatile noise from BURN ticks, comparator dice, and stub-effect resolutions; it does not track who is closest to winning.
- **"Ties → unassigned" silently no-ops** the rule whenever multiple players are tied. Early-game and end-game both produce many ties. "Ties → all" keeps label-targeted rules firing, which is the watchable behaviour M1.5 needs.

WOUNDED stays argmin(chips) — chips is still the right vulnerability metric (it gates discard/redraw, shop access, BURN survival). Only the tie-break flips.

The other two labels (GENEROUS, CURSED) stay defined per the original `state.md` semantics (argmax of cards_given / burn) but adopt the same "ties → all" rule for consistency. They land with M2.

## Decision

The canonical floating-label definitions are:

| Label | Definition | Tie-break |
|---|---|---|
| THE LEADER | argmax(player.vp) | ties → all tied players hold the label |
| THE WOUNDED | argmin(player.chips) | ties → all tied players hold the label |
| THE GENEROUS | argmax(player.history.cards_given_this_game) | ties → all tied players (zero → empty) |
| THE CURSED | argmax(player.status.burn) | ties → all tied players (zero → empty) |

`design/state.md:61-67` is updated to reflect this. `engine/src/rulso/labels.py` (RUL-19, PR #11) already implements LEADER/WOUNDED per this spec.

## Consequences

- A label-targeted rule no longer silently no-ops on tied state — it scopes to every tied player. Effect application then runs N times. Verify `effects._scope_subject` handles `len(scope) > 1` cleanly when the scope-wiring ticket (RUL-22) lands.
- The "no matches" path (rule references a label that genuinely no player holds — e.g. zero-burn means CURSED is empty) still resolves the rule with no effect, per `state.md`'s existing semantics. Empty player set also still produces empty frozensets.
- Renderer / UI must handle the multi-holder case in narration ("THE LEADER (p0, p2)") rather than assuming a single holder. Defer until M2 when GENEROUS / CURSED join the live set.
- LEADER is now derivable from a vp delta after every `_apply_stub_effect` and (eventually) every effect-card resolution. The recompute call in `rules.enter_round_start` still runs once per round per `state.md` — intra-round vp changes don't retrigger label recomputation. If that becomes a correctness issue (e.g. WHEN rules that need fresh labels mid-resolve), revisit in M2.

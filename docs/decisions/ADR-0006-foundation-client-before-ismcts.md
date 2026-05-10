# ADR-0006 — Foundation/Minimal Client lands before ISMCTS

**Status**: Accepted (2026-05-10)

## Context

The original `roadmap.md` ordering was M1 → M1.5 → M2 → **M3 ISMCTS** → **M4 Pixi client** → M5 polish. The premise: ISMCTS bots are "non-negotiable" because heuristic bots won't surface design flaws in solo play (`PROJECT_CONTEXT.md` "Critical context"), so smart opponents come before the rendering work.

After M2 closed (2026-05-10) the user attempted CLI playtesting via `rulso --human-seat 0` (RUL-52). Two problems surfaced inside the first round:

1. **Decision-support is missing.** The TTY prompt dumps card IDs (`mod.cmp.gt`), an active rule template with no semantic preview of what completing it does, no goal cards, no opponents' chips/VP/labels, and a flat enumeration of every legal action including all `C(7,1..3) = 63` discard combos. The human can submit a legal action; the human cannot make a *meaningful* one.
2. **Bot strength is not the bottleneck.** Even with perfect ISMCTS opponents, the same prompt would be unplayable. The missing piece is rendering, not opponent intelligence.

This inverts the original premise: ISMCTS provides design signal **only when the human can play the other seats well enough to feel the game**. CLI prompts cannot reach that bar without becoming something close to a UI; at that point we are building rendering primitives twice.

A second factor: ISMCTS payoff design wants playtest signal as input. Heuristics for "what counts as a good move" are easier to scope after a human has played 20 hands than from cold reasoning over `cards.yaml`. Ordering the client first lets M4 ISMCTS draw on real session data.

## Decision

Reorder the post-M2 milestones:

| Milestone | Old | New |
|---|---|---|
| M3 | ISMCTS bot | **Foundation/Minimal Client** |
| M4 | Pixi client | **Smart bot (ISMCTS)** |
| M5 | Polish | Polish (unchanged) |

A pre-M3 sweep — informally **M2.5 — Mechanic gaps** — closes three known-unwired M2 mechanics before the client work begins:

- SHOP content (RUL-56, already filed) — `shop_cards:` is empty; SHOP fires every 3 rounds but offers nothing
- MARKED consumer wiring — `APPLY_MARKED` handler exists but no effect card produces it, and `EACH_PLAYER` scoping at `effects.py:414` ignores MARKED entirely
- Status data completeness — `cards.yaml effect_cards:` is missing `eff.marked.apply` and `eff.chained.clear`; CHAINED is currently a one-way trip

These do not warrant a separate milestone parent in Linear; they ship as `parent = RUL-24` (M2) follow-ups before M3 dispatches.

### Foundation/Minimal Client scope (M3)

**In scope** — anything required to playtest with informed decisions:

- Engine WebSocket protocol (`engine/src/rulso/protocol.py`, currently empty) — Pydantic message envelopes, full-state broadcast on every transition, action-submit envelope from client
- Engine WebSocket server (`engine/src/rulso/server.py`, currently empty) — asyncio loop, one human seat per connection, bots fill the rest
- `client/` bootstrap: Vite + Pixi v8 + TypeScript per `tech.md`
- TypeScript-from-Pydantic type generation pipeline (`scripts/regenerate-types.sh`)
- Rendering for decision support: hand with full card text, active rule with semantic preview ("if you complete this rule with GT, it reads `IF p2 GT 2d6 ROUNDS → eff.noop`"), 3 active goal cards with claim conditions visible, all 4 opponents' public state (chips, VP, hand size, status tokens, floating labels), revealed effect for the round
- Input: click-to-play onto a slot (drag-drop is M5), discard via card-toggle (not flat enumeration), JOKER attachment, dice-mode pick where the comparator is OP-only
- Basic dice-roll text/output (no animation)
- Wire `bots/human` through the WebSocket (replace TTY driver with WS-backed driver) — `bots/random` continues to fill the other three seats

**Out of scope** — owned by M5 Polish:

- Aegean palette, JetBrains Mono / Inter typography
- Animations (card draw, slot fill, rule resolve, dice roll, status apply, VP claim)
- Sound (every event from `aesthetic.md` audio table)
- Iconography for status tokens
- Drag-drop (click is enough for decision-making)
- Mobile / touch
- Settings UI

**Out of scope** — owned by M4 ISMCTS:

- Smart opponent strategy
- ISMCTS rollouts, sampling, decision-rationale logging

The DoD bar for M3 is "ugly but playable": a human can sit down, read the board, make a meaningful decision, and reach a winner. Visual quality is not measured.

### Substrate-first within M3

Per the protocol: foundational types and contracts before features. The M3 fan-in order:

1. **WebSocket protocol shape** — Pydantic envelopes for state-broadcast and action-submit, generated TS types. Substrate spike + ratification ADR.
2. **Engine server** — asyncio loop, connection management, broadcast on transition.
3. **Client bootstrap** — Vite/Pixi/TS scaffold, WS connection, parse-and-store state.
4. **Rendering** — fan: hand, active rule, goals, opponents, status row, revealed effect.
5. **Input** — fan: play_card, discard, play_joker, OP-only dice picker.
6. **Human-seat wire-through** — replace TTY with WS-backed driver; CLI keeps working.

## Consequences

- **`roadmap.md`** rewrites M3, M4, M5 sections. M3 inherits the bulk of the old M4 DoD, minus polish. M4 inherits the old M3 DoD verbatim. M5 inherits the polish bullets that previously lived in old M4.
- **`PROJECT_CONTEXT.md`** — "Smart bots are non-negotiable" line stays in critical context (it's still true; the *order* changes, not the necessity). Active ADRs list grows by one.
- **`STATUS.md`** — captures the reorder, the M2.5 gap-close set, and the M3 substrate-spike entry point.
- **Linear** — M3 (Foundation Client) and M4 (ISMCTS) parent issues open; sub-issues for the M2.5 gap-close set open and dispatchable in parallel.
- **Tech stack lock unchanged.** `tech.md` already names Vite + Pixi v8 + TypeScript + websockets + Pydantic v2; no stack ADR needed for M3.
- **Bots remain weighted-random for the duration of M3.** Foundation Client human play will be against `bots/random`. The user's experience of opponent strength will be poor — playtest signal targets card balance, rule grammar feel, and pacing, not opponent challenge. This is acknowledged and accepted.
- **ISMCTS payoff design moves downstream of playtest data.** M4 scoping reads from CLI-and-client session traces, not from cold theory.
- **Risk: M3 is the largest milestone in the project so far.** Original M4 DoD was already wide; even minus polish the surface is engine + client + protocol + types + rendering + input. Mitigated by substrate-first sequencing and a deliberately ugly DoD bar.

## Alternatives considered

**(a) Keep original ordering — ship ISMCTS first, then build the client.** Rejected. The rendering gap blocks playtesting regardless of bot strength; ISMCTS without a usable surface generates no design signal.

**(b) Solve the rendering problem inside the CLI — extend `bots/human` with rich text rendering, a pseudo-board, a discard sub-prompt.** Considered but rejected. Reaches a usable bar at maybe 60% of the work of a real client; produces zero artefacts that survive into M3/M5; and the rendering primitives (goal text, rule semantic preview, opponent projection) are exactly what the real client also needs to render. Worse: a half-built CLI surface invites feature creep ("just add this one more thing") that delays the real fix.

**(c) Scope a "minimal CLI playable" interim before Foundation Client.** Same fail mode as (b); extends timeline without producing reusable artefacts.

**(d) Wait for ISMCTS bot to ship before client work, but file the rendering gap as a separate stream.** Rejected — the user can't playtest in either world until the client lands. Parallelising doesn't help when the path between any work product and the user requires the client.

# ADR-0008 — WebSocket protocol envelope shape (M3 substrate)

**Status**: Accepted (2026-05-11)

## Context

ADR-0006 reorders the post-M2 milestones to land Foundation/Minimal Client (M3) before ISMCTS (M4). Substrate-first sequencing inside M3 puts the WebSocket protocol shape at the head of the fan: server, client bootstrap, rendering, and input all consume envelopes whose shape must be ratified before any of them lands. `engine/src/rulso/protocol.py` was empty pre-spike; `tech.md` carries informal hints (snake_case JSON, full-state-on-every-change for MVP) that this ADR promotes to Pydantic-validated substrate.

Two coupled questions surfaced inside the spike:

1. **Envelope shape and broadcast cadence** — what Pydantic models live in `protocol.py` and when does the server emit them?
2. **Action-submit shape** — does the client submit (a) an opaque action-id echoed back from `bots.random.enumerate_legal_actions`, or (b) a structured payload (`play_card` / `play_joker` / `discard_redraw`) per the existing engine action shape?

Both lock the wire contract every downstream M3 sub-issue consumes. They are ratified together (one ADR) because the cadence is a direct consequence of the envelope shape under MVP — see "Alternatives considered".

## Decision

### Envelopes

Server → client union (discriminator: `type`):

| Variant | Field shape | When emitted |
|---|---|---|
| `Hello` | `{type: "hello", seat: int, protocol_version: int}` | Once, on connection accepted. Pins seat + protocol version. |
| `StateBroadcast` | `{type: "state", state: GameState}` | After every engine transition that mutates `GameState`. |
| `ErrorEnvelope` | `{type: "error", code: ErrorCode, message: str}` | On invalid submission (protocol- or legality-level). Server does not disconnect. |

Client → server union (discriminator: `type`):

| Variant | Field shape | When sent |
|---|---|---|
| `ActionSubmit` | `{type: "action_submit", action: PlayCard \| PlayJoker \| DiscardRedraw}` | Client picks one structured action for the active turn. |

`ErrorCode` is a `StrEnum`: `protocol_invalid` / `not_your_turn` / `illegal_action` / `unknown_action` / `internal_error`. Additive — new variants extend the enum without a protocol-version bump.

`PROTOCOL_VERSION = 1`. Incompatible envelope changes bump it. Additive variants (new enum values, new envelope types as future union members) do not.

### Broadcast cadence (MVP)

Engine emits `StateBroadcast` on every transition that mutates `GameState`: phase change, action applied, status tick, shop resolution, dice roll. Single-player, low-frequency traffic; a diff protocol is a future optimisation per `tech.md` §Protocol. The cadence is not a contract — only the envelope shape is — so a future tuning ticket can introduce coalescing without bumping `PROTOCOL_VERSION`.

### Action-submit shape — locked as (b) structured

`ActionSubmit.action` carries the engine's existing action union from `rulso.bots.random`: `PlayCard | PlayJoker | DiscardRedraw`. `Pass` is intentionally excluded — the server selects `Pass` automatically when `enumerate_legal_actions` returns empty; clients never submit it.

The action shapes are **imported, not redefined**. `protocol.py` references `rulso.bots.random.PlayCard` etc. directly, so the wire format and the engine's internal action model are one and the same — no structural drift is possible. The inner discriminator stays `kind` (existing engine convention); the outer envelope discriminator is `type`. Different fields, no collision.

Server authority is preserved: on `ActionSubmit`, the server re-enumerates legal actions for the submitter's seat via `bots.random.enumerate_legal_actions` and validates structural equality before applying. The structured payload is a hint, never trusted on its face.

Rationale:

- **Click-driven UI naturally constructs structured payloads.** User clicks card → clicks slot → picks dice mode → client builds `PlayCard{card_id, slot, dice}` from the inputs. Shape (a) (opaque ids) would require the server to pre-render every legal action's structured description into the state broadcast for the client to render menus from — strictly more wire data, no rendering win.
- **Engine action model already has the shape.** `bots.random.PlayCard | PlayJoker | DiscardRedraw` are Pydantic v2 discriminated-union members today (`bots/human` exercises them as a menu). Reusing them eliminates a duplicate type surface and a synchronisation tax between protocol and engine.
- **`Pass` asymmetry.** The bot returns `Pass()` when no legal action exists; a human-driven seat doesn't volunteer a Pass — the server picks it on stalled stdin (matches `bots/human` EOF behaviour). Modelling `Pass` as a client-submittable action would let a malicious client skip its turn arbitrarily. Excluding it server-side keeps the rule clean.
- **Forward compatibility.** Adding a new action variant (e.g. `Resign`, `ClaimGoal`) is one new `BaseModel` subclass plus one new member in the `Annotated` union — additive, no version bump.

## Consequences

- **`engine/src/rulso/protocol.py`** populated with the envelope hierarchy and `PROTOCOL_VERSION`. Imports `PlayCard / PlayJoker / DiscardRedraw` from `rulso.bots.random` (no substrate edit there). Imports `GameState` from `rulso.state` (additive consumer; `state.py` is untouched).
- **`engine/tests/test_protocol.py`** (20 tests) pins: round-trip on every envelope variant; discriminator dispatch on both unions; validation failures the server emits `ErrorCode.PROTOCOL_INVALID` on (unknown type, missing type, unknown action kind, malformed action payload, invalid error code, negative seat); `Pass` rejection at the client→server surface.
- **`engine/src/rulso/server.py`** stays empty — out of scope for this spike. The server ticket (next M3 sub-issue) consumes the locked envelopes via `TypeAdapter[ServerEnvelope]` / `TypeAdapter[ClientEnvelope]`.
- **TypeScript type generation** (per `tech.md` §"Type generation") will scan `protocol.py` + `state.py`. The discriminated-union pattern Pydantic emits maps cleanly to TypeScript tagged unions via `pydantic-to-typescript` / `datamodel-code-generator`. The pipeline lands as its own M3 sub-issue.
- **`bots.random` becomes the de-facto canonical action surface.** The "Open judgment calls" item in `STATUS.md` (promote action shapes to `legality.py` or `actions.py`) remains open. The protocol module's import of `PlayCard / PlayJoker / DiscardRedraw` makes the promotion a future find-and-replace — both `protocol.py` and `bots/human.py` would re-point at the new home. No protocol-version bump needed (structural shape unchanged).
- **Authoritative validation lives in the server**, not on the wire. The structured action payload is a hint; the server re-enumerates legal actions per turn and rejects mismatches with `ErrorEnvelope{code: ILLEGAL_ACTION}`. The client never assumes its submitted action will land — every action's outcome arrives via the next `StateBroadcast`.

## Alternatives considered

**(a) Opaque action-id submission.** Server enumerates legal actions, assigns each a stable id (e.g. tuple index for the turn), embeds the rendered description into the state broadcast. Client picks one and submits `{type: "action_submit", action_id: 0}`. Rejected: requires the server to ship rendered descriptions for every legal action alongside the state on every turn (significantly larger broadcasts); requires the client to render exclusively from server-supplied descriptions (less flexibility for the click-driven UI); duplicates the legality enumeration's effect into the broadcast envelope. Net: more wire data, less client flexibility, no upside vs structured payloads under server-authoritative validation.

**(b) Structured action submission.** Selected. See "Decision" above.

**(c) Two ADRs — envelope shape and broadcast cadence ratified separately.** Considered. Rejected for this spike: under MVP cadence (full-state-every-transition) the cadence is a direct consequence of the envelope shape, and a separate cadence ADR would carry one paragraph of decision. A future tuning ticket that introduces coalescing or diff broadcasts will warrant its own ADR — at that point cadence becomes a non-trivial decision. Keeping the two locked together here matches ADR-0007's "lock the shape, leave tuning open" precedent.

**(d) Flat client→server union with no nested `action` field.** I.e. `{type: "play_card", card_id, slot}` directly, no `action_submit` wrapper. Matches `tech.md`'s informal hint verbatim. Rejected: collides the envelope discriminator namespace (`type`) with the action discriminator namespace. Adding a non-action client envelope later (e.g. `ReplayRequest`) would either require renaming every action's `type` to `kind` (engine-wide breaking change) or accepting an inconsistent envelope shape. The nested wrapper costs one extra field per submission and keeps the two namespaces clean.

**(e) Include an `EventNotification{type: "event", name: str, payload: dict}` envelope in the M3 substrate.** Considered — `tech.md` mentions event broadcasts for rule resolution. Rejected for this spike: the engine doesn't emit events yet, and an event taxonomy without concrete variants is dead substrate. Future M5 polish (animations, sound) will add events as an additive `ServerEnvelope` member. Adding them now bakes in a dict-typed payload escape hatch that future variants would inherit.

**(f) `Pass` as a client-submittable action.** Rejected. Lets a client volunteer-pass on a turn where legal actions exist — opens a turn-skipping loophole. The server's automatic `Pass` selection on empty enumeration is the only correct path.

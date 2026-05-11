/* tslint:disable */
/* eslint-disable */
/**
/* This file was automatically generated from pydantic models by running pydantic2ts.
/* Do not modify it by hand - just update the pydantic models and then re-run the script
*/

/**
 * Error categories an engine may emit to a client.
 *
 * Additive: new variants extend this enum without protocol-version bump.
 */
export type ErrorCode = "protocol_invalid" | "not_your_turn" | "illegal_action" | "unknown_action" | "internal_error";
export type Phase = "lobby" | "round_start" | "build" | "resolve" | "shop" | "end";
export type CardType = "SUBJECT" | "NOUN" | "MODIFIER" | "JOKER" | "EFFECT";
export type RuleKind = "IF" | "WHEN" | "WHILE";

/**
 * Client → server: submit one action for the active turn.
 *
 * The wrapped :data:`ClientAction` carries the engine's existing action
 * shape. The server re-enumerates legal actions for the submitter's seat
 * and validates structural equality before applying — never trusts the
 * submitted payload's legality on its face.
 */
export interface ActionSubmit {
  type?: "action_submit";
  action: PlayCard | PlayJoker | DiscardRedraw;
}
/**
 * Play one card from hand into one open slot.
 *
 * ``dice`` is 1 (1d6) or 2 (2d6) when the card is a MODIFIER — under the M1
 * stub every MODIFIER play is treated as a comparator. ``None`` otherwise.
 */
export interface PlayCard {
  kind?: "play_card";
  card_id: string;
  slot: string;
  dice?: (1 | 2) | null;
}
/**
 * Attach a JOKER from hand to the active rule (RUL-45).
 *
 * JOKERs do not fill a slot; they bind to ``RuleBuilder.joker_attached``
 * via ``rules.play_joker``. One joker per rule per ``design/state.md``.
 */
export interface PlayJoker {
  kind?: "play_joker";
  card_id: string;
}
/**
 * Spend chips to discard 1..3 cards and redraw.
 */
export interface DiscardRedraw {
  kind?: "discard_redraw";
  card_ids: string[];
}
/**
 * Server → client protocol/legality violation.
 *
 * ``code`` keeps the categorisation machine-readable; ``message`` is the
 * human-readable explanation. The server does not disconnect on protocol
 * error — it returns the envelope and waits for a corrected submission.
 */
export interface ErrorEnvelope {
  type?: "error";
  code: ErrorCode;
  message: string;
}
/**
 * Top-level immutable game state.
 *
 * Update via ``model_copy``::
 *
 *     next_state = state.model_copy(
 *         update={"phase": Phase.BUILD, "active_seat": 1},
 *     )
 */
export interface GameState {
  phase?: Phase;
  round_number?: number;
  dealer_seat?: number;
  active_seat?: number;
  players?: Player[];
  deck?: Card[];
  discard?: Card[];
  effect_deck?: Card[];
  effect_discard?: Card[];
  goal_deck?: GoalCard[];
  goal_discard?: GoalCard[];
  active_goals?: (GoalCard | null)[];
  shop_deck?: Card[];
  shop_pool?: ShopOffer[];
  shop_offer?: ShopOffer[];
  shop_discard?: ShopOffer[];
  active_rule?: RuleBuilder | null;
  persistent_rules?: PersistentRule[];
  last_roll?: LastRoll | null;
  winner?: Player | null;
  build_turns_taken?: number;
  revealed_effect?: Card | null;
}
export interface Player {
  id: string;
  seat: number;
  chips?: number;
  vp?: number;
  hand?: Card[];
  status?: PlayerStatus;
  history?: PlayerHistory;
  [k: string]: unknown;
}
export interface Card {
  id: string;
  type: CardType;
  name: string;
  scope_mode?: "singular" | "existential" | "iterative";
  [k: string]: unknown;
}
export interface PlayerStatus {
  burn?: number;
  mute?: boolean;
  blessed?: boolean;
  marked?: boolean;
  chained?: boolean;
  [k: string]: unknown;
}
export interface PlayerHistory {
  rules_completed_this_game?: number;
  cards_given_this_game?: number;
  hits_taken_this_game?: number;
  last_round_was_hit?: boolean;
  [k: string]: unknown;
}
/**
 * Goal card — face-up VP-award objective per ``design/goals-inventory.md``.
 *
 * Lives in its own deck (``GameState.goal_deck`` / ``goal_discard`` /
 * ``active_goals``); not a :class:`Card` because its payload (predicate id,
 * VP award, claim kind) doesn't fit the uniform ``Card`` shape.
 *
 * ``claim_condition`` is a **registry key** (snake_case predicate id), not
 * an expression — the engine resolves it to a function ``(player, state) →
 * bool`` at evaluation time. ``claim_kind`` controls life-cycle: ``"single"``
 * discards on first match and replenishes from ``goal_deck``; ``"renewable"``
 * stays face-up and awards ``vp_award`` to every matching player each round.
 */
export interface GoalCard {
  id: string;
  name: string;
  claim_condition: string;
  vp_award: number;
  claim_kind: "single" | "renewable";
  [k: string]: unknown;
}
/**
 * One shop offer: a priced :class:`Card` purchasable during the SHOP phase.
 *
 * Wraps an existing :class:`Card` payload with a chip ``price``. When a
 * player buys the offer the wrapped ``card`` is appended to ``Player.hand``
 * (counts against ``HAND_SIZE`` per ``design/state.md`` SHOP step 3). Unsold
 * offers move to ``GameState.shop_discard`` and recycle into
 * ``GameState.shop_pool`` on next-shop draw when the pool empties.
 */
export interface ShopOffer {
  card: Card;
  price: number;
  [k: string]: unknown;
}
export interface RuleBuilder {
  template: RuleKind;
  slots?: Slot[];
  plays?: Play[];
  joker_attached?: Card | null;
  [k: string]: unknown;
}
export interface Slot {
  name: string;
  type: CardType;
  filled_by?: Card | null;
  modifiers?: Card[];
  [k: string]: unknown;
}
export interface Play {
  player_id: string;
  card: Card;
  slot: string;
  [k: string]: unknown;
}
/**
 * A WHEN or WHILE rule locked into play.
 *
 * `kind` is restricted to ``RuleKind.WHEN`` or ``RuleKind.WHILE``;
 * ``IF`` rules are one-shot and never persist.
 */
export interface PersistentRule {
  kind: RuleKind;
  rule: RuleBuilder;
  created_round: number;
  created_by: string;
  [k: string]: unknown;
}
export interface LastRoll {
  player_id: string;
  value: number;
  dice_count: number;
  [k: string]: unknown;
}
/**
 * Server → client greeting, sent once after a connection is accepted.
 *
 * Assigns the human's seat and pins the protocol version. Subsequent
 * incompatible envelope changes bump :data:`PROTOCOL_VERSION`.
 */
export interface Hello {
  type?: "hello";
  seat: number;
  protocol_version: number;
}
/**
 * Server → client full-state push.
 *
 * Sent on every engine transition that mutates ``GameState`` (phase change,
 * action applied, status tick, shop resolution). MVP cadence is "every
 * transition" per ADR-0008; a diff protocol is a future additive variant.
 *
 * ``legal_actions`` is populated only on broadcasts where the human seat is
 * active in BUILD — the client renders one button per entry and submits the
 * chosen action via :class:`ActionSubmit`. ``None`` on every other broadcast
 * (bot turns, non-BUILD phases, terminal state). Additive per ADR-0008
 * §Consequences — no ``PROTOCOL_VERSION`` bump.
 */
export interface StateBroadcast {
  type?: "state";
  state: GameState;
  legal_actions?: (PlayCard | PlayJoker | DiscardRedraw)[] | null;
}

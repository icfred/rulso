// Hand-curated unions over the generated interfaces.
//
// `pydantic-to-typescript` emits every BaseModel subclass it finds in
// `rulso.protocol` but does not expose the module-level `Annotated[Union[...],
// Field(discriminator=...)]` aliases (those are TypeAdapter aliases, not
// BaseModel subclasses). Pydantic v2 marks the discriminator field optional in
// the schema because it carries a default; in practice every envelope on the
// wire includes it, so the literal-typed `type` / `kind` fields below produce
// the discriminated-union narrowing TypeScript expects.

import type {
  ActionSubmit,
  Card,
  DiscardRedraw,
  ErrorEnvelope,
  GameState,
  GoalCard,
  Hello,
  Play,
  PlayCard,
  PlayJoker,
  Player,
  RuleBuilder,
  Slot,
  StateBroadcast,
} from "./generated";

export type ServerEnvelope =
  | (Hello & { type: "hello" })
  | (StateBroadcast & { type: "state" })
  | (ErrorEnvelope & { type: "error" });

export type ClientAction =
  | (PlayCard & { kind: "play_card" })
  | (PlayJoker & { kind: "play_joker" })
  | (DiscardRedraw & { kind: "discard_redraw" });

export type ClientEnvelope = ActionSubmit & { type: "action_submit" };

export type {
  ActionSubmit,
  Card,
  DiscardRedraw,
  ErrorEnvelope,
  GameState,
  GoalCard,
  Hello,
  Play,
  PlayCard,
  PlayJoker,
  Player,
  RuleBuilder,
  Slot,
  StateBroadcast,
};

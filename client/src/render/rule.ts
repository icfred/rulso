// Render the active rule's build state as a one-line semantic preview.
//
// IF rules look like ``IF [SUBJECT: …] HAS [QUANT: …] [NOUN: …] THEN [EFFECT: …]``.
// Empty slots render as ``[<TYPE>: ?]``; unrevealed effects render as
// ``[EFFECT: ?]``. A JOKER attached to the rule is appended as ``+ JOKER:…``.
//
// Slot ordering follows the engine's CONDITION template — SUBJECT then QUANT
// then NOUN per the M2 vocabulary in ``design/cards.yaml``. The renderer
// trusts ``RuleBuilder.slots`` ordering rather than re-sorting; the engine
// always emits slots in CONDITION-template order.

import type { Card, GameState, RuleBuilder, Slot } from "../types/envelopes";
import { renderCard } from "./cards";

const CONNECTORS: Record<string, string> = {
  SUBJECT: "",
  QUANT: "HAS",
  NOUN: "",
};

export function renderActiveRule(state: GameState): string {
  const rule = state.active_rule ?? null;
  if (!rule) return "(no active rule)";
  const slotsText = renderSlots(rule);
  const effectText = renderEffect(state.revealed_effect ?? null);
  const joker = rule.joker_attached ? ` + ${renderCard(rule.joker_attached)}` : "";
  return `${rule.template} ${slotsText} THEN ${effectText}${joker}`;
}

function renderSlots(rule: RuleBuilder): string {
  const slots = rule.slots ?? [];
  const parts: string[] = [];
  for (const slot of slots) {
    const connector = CONNECTORS[slot.name];
    if (connector) parts.push(connector);
    parts.push(renderSlot(slot));
  }
  return parts.join(" ");
}

function renderSlot(slot: Slot): string {
  const filled = slot.filled_by ?? null;
  const body = filled ? renderCard(filled) : "?";
  const mods = (slot.modifiers ?? []) as Card[];
  const modText = mods.length > 0 ? ` ${mods.map((m) => renderCard(m)).join(" ")}` : "";
  return `[${slot.name}: ${body}${modText}]`;
}

function renderEffect(effect: Card | null): string {
  return effect ? `[EFFECT: ${renderCard(effect)}]` : "[EFFECT: ?]";
}

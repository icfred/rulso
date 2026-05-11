// Render the active rule's build state across multiple lines.
//
// Line 1 — semantic preview of the rule template + slots:
//   ``IF [SUBJECT: …] HAS [QUANT: …] [NOUN: …] THEN [EFFECT: …]``
//
// Line 2+ — for each unfilled slot, a list of the human's hand cards that
// could fill it (so the playtester can map a card to a slot without
// memorising the legal-actions output). Filter rule: card type === slot type.
//
// Effect prediction — when ``state.revealed_effect`` is set, a `Effect:` line
// renders the effect card text so the player can plan the resolve outcome.
//
// JOKER attached — if `rule.joker_attached` is non-null, append it after the
// preview as ``+ JOKER:VARIANT``.
//
// Slot ordering follows the engine's CONDITION template — SUBJECT then QUANT
// then NOUN per the M2 vocabulary in `design/cards.yaml`. The renderer trusts
// `RuleBuilder.slots` ordering rather than re-sorting; the engine always emits
// slots in CONDITION-template order.

import type { Card, GameState, Player, RuleBuilder, Slot } from "../types/envelopes";
import { renderCard } from "./cards";

const CONNECTORS: Record<string, string> = {
  SUBJECT: "",
  QUANT: "HAS",
  NOUN: "",
};

export interface RuleLine {
  text: string;
}

export function renderRulePanel(state: GameState, humanSeat: number | null): RuleLine[] {
  const rule = state.active_rule ?? null;
  if (!rule) return [{ text: "(no active rule)" }];

  const lines: RuleLine[] = [];
  lines.push({ text: renderHeadline(rule) });

  if (state.revealed_effect) {
    lines.push({ text: `  Effect: ${renderCard(state.revealed_effect)}` });
  }

  if (rule.joker_attached) {
    lines.push({ text: `  JOKER attached: ${renderCard(rule.joker_attached)}` });
  }

  const hand = handFor(state, humanSeat);
  if (hand.length > 0) {
    for (const slot of (rule.slots ?? []) as Slot[]) {
      const fillers = candidatesFor(slot, hand);
      if (slot.filled_by) continue;
      if (fillers.length === 0) {
        lines.push({ text: `  ${slot.name} ← (no playable card in hand)` });
      } else {
        const names = fillers.map((c) => `${c.id}:${renderCard(c)}`).join(", ");
        lines.push({ text: `  ${slot.name} ← ${names}` });
      }
    }
  }

  return lines;
}

function renderHeadline(rule: RuleBuilder): string {
  const slotsText = renderSlots(rule);
  const effectText = renderEffectSlot();
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

function renderEffectSlot(): string {
  // The active rule itself does not carry an effect slot post-RUL-31 — the
  // effect lives on `state.revealed_effect` once revealed. The headline keeps
  // ``[EFFECT: ?]`` for visual symmetry until the resolve step consumes it,
  // and the dedicated ``Effect:`` line shows the concrete card text.
  return "[EFFECT: ?]";
}

function handFor(state: GameState, humanSeat: number | null): readonly Card[] {
  if (humanSeat === null) return [];
  const me = (state.players ?? []).find((p: Player) => p.seat === humanSeat);
  return me?.hand ?? [];
}

function candidatesFor(slot: Slot, hand: readonly Card[]): readonly Card[] {
  return hand.filter((card) => card.type === slot.type);
}

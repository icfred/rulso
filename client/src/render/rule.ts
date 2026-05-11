// Render the active rule's build state across multiple lines.
//
// Line 1 — semantic preview of the rule template + slots, with the round's
// revealed effect rendered inline in the EFFECT position:
//   ``IF [SUBJECT: …] HAS [QUANT: …] [NOUN: …] THEN [EFFECT: <revealed_effect>]``
// EFFECT is NOT a player-fillable slot (engine has no SlotKind.EFFECT use); it
// comes from ``state.revealed_effect`` drawn at round_start. Inline rendering
// avoids the "[EFFECT: ?] = nothing happened" misread that surfaced in early
// playtest. Pre-reveal (no revealed_effect yet) renders ``[EFFECT: ?]``.
//
// Line 2+ — for each unfilled slot, a list of the human's hand cards that
// could fill it (so the playtester can map a card to a slot without
// memorising the legal-actions output). Filter rule: card type === slot type.
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

  const revealedEffect = state.revealed_effect ?? null;
  const lines: RuleLine[] = [];
  lines.push({ text: renderHeadline(rule, humanSeat, revealedEffect) });

  if (rule.joker_attached) {
    lines.push({ text: `  JOKER attached: ${renderCard(rule.joker_attached, humanSeat)}` });
  }

  const hand = handFor(state, humanSeat);
  if (hand.length > 0) {
    for (const slot of (rule.slots ?? []) as Slot[]) {
      const fillers = candidatesFor(slot, hand);
      if (slot.filled_by) continue;
      if (fillers.length === 0) {
        lines.push({ text: `  ${slot.name} ← (no playable card in hand)` });
      } else {
        const names = fillers.map((c) => renderCard(c, humanSeat)).join(", ");
        lines.push({ text: `  ${slot.name} ← ${names}` });
      }
    }
  }

  return lines;
}

export function renderActiveRule(
  rule: RuleBuilder,
  humanSeat: number | null,
  revealedEffect: Card | null = null,
): string {
  return renderHeadline(rule, humanSeat, revealedEffect);
}

function renderHeadline(
  rule: RuleBuilder,
  humanSeat: number | null,
  revealedEffect: Card | null,
): string {
  const slotsText = renderSlots(rule, humanSeat);
  const effectText = renderEffectSlot(revealedEffect, humanSeat);
  const joker = rule.joker_attached ? ` + ${renderCard(rule.joker_attached, humanSeat)}` : "";
  return `${rule.template} ${slotsText} THEN ${effectText}${joker}`;
}

function renderSlots(rule: RuleBuilder, humanSeat: number | null): string {
  const slots = rule.slots ?? [];
  const parts: string[] = [];
  for (const slot of slots) {
    const connector = CONNECTORS[slot.name];
    if (connector) parts.push(connector);
    parts.push(renderSlot(slot, humanSeat));
  }
  return parts.join(" ");
}

function renderSlot(slot: Slot, humanSeat: number | null): string {
  const filled = slot.filled_by ?? null;
  const body = filled ? renderCard(filled, humanSeat) : "?";
  const mods = (slot.modifiers ?? []) as Card[];
  const modText = mods.length > 0 ? ` ${mods.map((m) => renderCard(m, humanSeat)).join(" ")}` : "";
  return `[${slot.name}: ${body}${modText}]`;
}

function renderEffectSlot(revealedEffect: Card | null, humanSeat: number | null): string {
  // EFFECT is not a player-fillable slot — it comes from
  // ``state.revealed_effect`` drawn at round_start. Render the revealed card
  // inline so players see what the round will do before committing cards;
  // ``?`` only when the effect hasn't been drawn yet (pre-round_start).
  if (revealedEffect === null) return "[EFFECT: ?]";
  return `[EFFECT: ${renderCard(revealedEffect, humanSeat)}]`;
}

function handFor(state: GameState, humanSeat: number | null): readonly Card[] {
  if (humanSeat === null) return [];
  const me = (state.players ?? []).find((p: Player) => p.seat === humanSeat);
  return me?.hand ?? [];
}

function candidatesFor(slot: Slot, hand: readonly Card[]): readonly Card[] {
  return hand.filter((card) => card.type === slot.type);
}

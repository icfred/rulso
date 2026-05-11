// Render the human's own seat — chips, VP, status, floating labels, plus the
// hand as a card list (one entry per `Card`, sorted into a stable order so
// the playtester can scan it the same way every broadcast).
//
// Sort order: SUBJECT → comparator-MODIFIER (QUANT-fillers) → NOUN →
// operator-MODIFIER → JOKER → EFFECT. Mirrors the natural read order of an
// IF rule (`IF [SUBJECT] HAS [QUANT] [NOUN]`) so the eye finds slot-fillers
// in the order the rule needs them. Worker's call per the hand-over — easy to
// revisit once the design team has a stronger opinion.

import type { Card, GameState } from "../types/envelopes";
import { renderCard } from "./cards";

const COMPARATOR_NAMES = new Set(["GE", "GT", "LE", "LT", "EQ"]);

export interface YouLine {
  text: string;
  card?: Card;
}

export function renderYou(state: GameState, humanSeat: number): YouLine[] {
  const me = (state.players ?? []).find((p) => p.seat === humanSeat);
  if (!me) return [{ text: `(no seat ${humanSeat} in state)` }];

  const lines: YouLine[] = [];
  const labels: string[] = [];
  for (const [name, holders] of Object.entries(state.labels ?? {})) {
    if (holders.includes(me.id)) labels.push(name);
  }
  if (me.status?.marked) labels.push("THE MARKED");
  if (me.status?.chained) labels.push("THE CHAINED");

  const s = me.status ?? {};
  const statusBits: string[] = [];
  if ((s.burn ?? 0) > 0) statusBits.push(`BURN(${s.burn})`);
  if (s.mute) statusBits.push("MUTE");
  if (s.blessed) statusBits.push("BLESSED");

  const labelText = labels.length > 0 ? ` [${labels.join(", ")}]` : "";
  const statusText = statusBits.length > 0 ? `, status: ${statusBits.join(", ")}` : "";
  const handSize = me.hand?.length ?? 0;
  lines.push({
    text: `You (seat ${me.seat})${labelText} — chips: ${me.chips ?? 0}, VP: ${me.vp ?? 0}, hand: ${handSize}${statusText}`,
  });

  const hand = [...(me.hand ?? [])].sort(sortHand);
  if (hand.length === 0) {
    lines.push({ text: "  (empty hand)" });
  } else {
    for (const card of hand) {
      lines.push({ text: `  [${card.type}] ${renderCard(card, humanSeat)}`, card });
    }
  }
  return lines;
}

function sortHand(a: Card, b: Card): number {
  const ao = sortBucket(a);
  const bo = sortBucket(b);
  if (ao !== bo) return ao - bo;
  return a.name.localeCompare(b.name);
}

function sortBucket(card: Card): number {
  if (card.type === "SUBJECT") return 0;
  if (card.type === "MODIFIER") {
    const head = card.name.split(":")[0] ?? card.name;
    return COMPARATOR_NAMES.has(head) ? 1 : 3;
  }
  if (card.type === "NOUN") return 2;
  if (card.type === "JOKER") return 4;
  if (card.type === "EFFECT") return 5;
  return 9;
}

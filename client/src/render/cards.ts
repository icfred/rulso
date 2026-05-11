// Render a Card to human-readable text for inline display.
//
// Mirrors engine card-name tokens defined in `design/cards.yaml`:
//   - SUBJECT  : "p0".."p3" (literal seats) | "THE LEADER"/"THE WOUNDED" (labels)
//                | "ANYONE"/"EACH_PLAYER" (polymorphic, scope_mode override)
//   - NOUN     : "VP" | "CHIPS" | "CARDS" | "RULES" | "HITS" | "GIFTS"
//                | "ROUNDS" | "BURN_TOKENS"
//   - MODIFIER : comparator "<OP>" or "<OP>:<N>" (OP ∈ {GE,GT,LE,LT,EQ}) |
//                operator  "AND" | "OR" | "BUT" | "MORE_THAN" | "AT_LEAST"
//   - JOKER    : "JOKER:<VARIANT>"
//   - EFFECT   : "<KIND>[:<MAG>][@<TARGET_MOD>]" — mirrors
//                `_parse_effect_name` in `engine/src/rulso/effects.py`.
//
// SUBJECT player ids render absolutely (`Player N` for `pN`) by default. The
// optional ``humanSeat`` argument flips the human's own seat to seat-relative
// `You` — passing it everywhere a card is rendered makes the human seat read
// naturally in transcript / opponents / rule preview / actions without
// drifting client/engine vocab for non-human seats.

import type { Card } from "../types/envelopes";

const COMPARATORS: Record<string, string> = {
  GE: "≥",
  GT: ">",
  LE: "≤",
  LT: "<",
  EQ: "=",
};

const OPERATORS: Record<string, string> = {
  AND: "AND",
  OR: "OR",
  BUT: "BUT",
  MORE_THAN: "MORE THAN",
  AT_LEAST: "AT LEAST",
};

export function renderCard(card: Card, humanSeat?: number | null): string {
  switch (card.type) {
    case "SUBJECT":
      return renderSubject(card, humanSeat);
    case "NOUN":
      return card.name;
    case "MODIFIER":
      return renderModifier(card);
    case "JOKER":
      return renderJoker(card);
    case "EFFECT":
      return renderEffect(card);
    default:
      return card.name;
  }
}

export function renderSeat(seat: number, humanSeat?: number | null): string {
  return humanSeat !== null && humanSeat !== undefined && seat === humanSeat
    ? "You"
    : `Player ${seat}`;
}

function renderSubject(card: Card, humanSeat?: number | null): string {
  const match = /^p(\d+)$/.exec(card.name);
  if (match) return renderSeat(Number(match[1]), humanSeat);
  if (card.name === "EACH_PLAYER") return "EACH PLAYER";
  return card.name;
}

function renderModifier(card: Card): string {
  const op = OPERATORS[card.name];
  if (op) return op;
  const [kind = "", num] = card.name.split(":");
  const sym = COMPARATORS[kind];
  if (!sym) return card.name;
  return num ? `${sym} ${num}` : sym;
}

function renderJoker(card: Card): string {
  const [, variant] = card.name.split(":");
  return variant ? `JOKER: ${variant}` : card.name;
}

function renderEffect(card: Card): string {
  const [body = card.name, targetToken] = card.name.split("@");
  const [kind = body, magStr] = body.split(":");
  const mag = magStr ? Number(magStr) : 1;
  const target = targetToken ? ` (${targetToken.toLowerCase().replace(/_/g, " ")})` : "";
  switch (kind) {
    case "GAIN_CHIPS":
      return `gain ${mag} chips${target}`;
    case "LOSE_CHIPS":
      return `lose ${mag} chips${target}`;
    case "GAIN_VP":
      return `gain ${mag} VP${target}`;
    case "LOSE_VP":
      return `lose ${mag} VP${target}`;
    case "DRAW":
      return `draw ${mag} cards${target}`;
    case "APPLY_BURN":
      return `apply BURN(${mag})${target}`;
    case "CLEAR_BURN":
      return `clear BURN${target}`;
    case "APPLY_MUTE":
      return `apply MUTE${target}`;
    case "APPLY_BLESSED":
      return `apply BLESSED${target}`;
    case "APPLY_MARKED":
      return `apply MARKED${target}`;
    case "APPLY_CHAINED":
      return `apply CHAINED${target}`;
    case "CLEAR_CHAINED":
      return `clear CHAINED${target}`;
    case "NOOP":
      return "no effect";
    default:
      return card.name;
  }
}

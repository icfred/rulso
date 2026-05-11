// Render the face-up goal slots — one human-readable line per slot plus an
// optional per-player progress line for predicates we can derive from the
// wire-shaped state without engine help.
//
// Coverage of the per-player progress lines:
//   * ``chips_at_least_75`` (THE_BANKER)   — list every player's chip count
//   * ``chips_under_10``    (THE_DEBTOR)   — list every player's chip count
//   * ``free_agent``        (THE_FREE_AGENT) — round number + status flags
//
// All other predicates render predicate text only; deriving them from state
// either needs history fields we don't surface in the client or a longer
// computation that would clutter the panel. Filed as follow-up; not blocking
// playtest signal.

import type { GameState, GoalCard, Player } from "../types/envelopes";

const PREDICATE_TEXT: Record<string, string> = {
  chips_at_least_75: "hold ≥ 75 chips",
  chips_under_10: "hold < 10 chips",
  rules_completed_at_least_3: "complete ≥ 3 rules",
  gifts_at_least_2: "give ≥ 2 cards",
  burn_at_least_2: "carry ≥ 2 BURN tokens",
  free_agent: "no status tokens by round 5",
  full_hand: "hold a full hand (7 cards)",
};

export interface GoalLine {
  text: string;
  indent: boolean;
}

export function renderGoals(state: GameState): GoalLine[] {
  const slots = state.active_goals ?? [];
  const lines: GoalLine[] = [];
  for (const [index, goal] of slots.entries()) {
    if (!goal) {
      lines.push({ text: `Goal ${index + 1}: (empty)`, indent: false });
      continue;
    }
    lines.push({ text: renderHeadline(index, goal), indent: false });
    for (const progress of progressLines(goal, state.players ?? [], state.round_number ?? 0)) {
      lines.push({ text: progress, indent: true });
    }
  }
  return lines;
}

function renderHeadline(index: number, goal: GoalCard): string {
  const text = PREDICATE_TEXT[goal.claim_condition] ?? goal.claim_condition;
  return `Goal ${index + 1}: ${goal.name} — ${text} (${goal.claim_kind}, ${goal.vp_award} VP)`;
}

function progressLines(goal: GoalCard, players: readonly Player[], roundNumber: number): string[] {
  switch (goal.claim_condition) {
    case "chips_at_least_75":
    case "chips_under_10":
      return [players.map((p) => `P${p.seat}:${p.chips ?? 0}`).join("  ")];
    case "free_agent":
      return [
        `round ${roundNumber} (need ≥ 5)`,
        ...players.map((p) => `P${p.seat}: ${statusSummary(p)}`),
      ];
    default:
      return [];
  }
}

function statusSummary(player: Player): string {
  const s = player.status ?? {};
  const bits: string[] = [];
  if ((s.burn ?? 0) > 0) bits.push(`BURN(${s.burn})`);
  if (s.mute) bits.push("MUTE");
  if (s.blessed) bits.push("BLESSED");
  if (s.marked) bits.push("MARKED");
  if (s.chained) bits.push("CHAINED");
  return bits.length === 0 ? "clean" : bits.join(",");
}

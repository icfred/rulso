// Render the face-up goal slots as one human-readable line per slot.
//
// `GoalCard.claim_condition` is a snake_case predicate id (see
// `engine/src/rulso/goals.py`); the engine catalogue ships the M2 starter set
// of 7 predicates. The map below mirrors that catalogue. Unknown ids fall
// back to the raw id so a future predicate is visible (not silently dropped)
// even before the lookup is updated — the divergence is acceptable per the
// hand-over (goals lookup is small + stable).

import type { GameState, GoalCard } from "../types/envelopes";

const PREDICATE_TEXT: Record<string, string> = {
  chips_at_least_75: "hold ≥ 75 chips",
  chips_under_10: "hold < 10 chips",
  rules_completed_at_least_3: "complete ≥ 3 rules",
  gifts_at_least_2: "give ≥ 2 cards",
  burn_at_least_2: "carry ≥ 2 BURN tokens",
  free_agent: "no status tokens by round 5",
  full_hand: "hold a full hand (7 cards)",
};

export function renderGoals(state: GameState): string[] {
  const slots = state.active_goals ?? [];
  return slots.map((goal, index) => renderSlot(goal ?? null, index));
}

function renderSlot(goal: GoalCard | null, index: number): string {
  if (!goal) return `Goal ${index + 1}: (empty)`;
  const text = PREDICATE_TEXT[goal.claim_condition] ?? goal.claim_condition;
  return `Goal ${index + 1}: ${goal.name} — ${text} (${goal.claim_kind}, ${goal.vp_award} VP)`;
}

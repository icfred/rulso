// Append-only narration over consecutive `StateBroadcast` payloads.
//
// `StateBroadcast.state` is the whole world after the transition — the engine
// does NOT emit per-event narration on the wire, so the client diffs two
// consecutive snapshots and produces a coarse human-readable log. The
// heuristics here are best-effort, not authoritative — see the stop-condition
// list in the hand-over. Cases the diff can't disambiguate cleanly (mainly
// chip-deltas around BURN tick + DiscardRedraw both costing chips) get a
// trailing "?" so the playtester sees uncertainty rather than a confident
// wrong attribution.
//
// Engine constants mirrored here to keep narration self-contained:
//
//   * ``BURN_TICK = 5``         (chips burned per BURN token at round_start)
//   * ``DISCARD_COST = 5``      (chips per card discarded)
//
// Both ratified by `engine/src/rulso/state.py`. The duplication is acceptable
// because the wire shape carries values, not formulas — bumping these in the
// engine without bumping this file produces narration that says "(cost 5
// chips)" while the engine charged 7; that's visible at smoke-test time and
// not a silent corruption.

import type { Card, GameState, GoalCard, Player, RuleBuilder, Slot } from "../types/envelopes";
import { renderCard, renderSeat } from "./cards";
import { renderActiveRule } from "./rule";

const BURN_TICK = 5;
const DISCARD_COST = 5;

export function diffStates(prev: GameState, curr: GameState, humanSeat: number | null): string[] {
  const lines: string[] = [];

  const prevRound = prev.round_number ?? 0;
  const currRound = curr.round_number ?? 0;

  // Round-transition narration runs BEFORE the per-player diff so the reader
  // sees `Round N resolved → effect` and `--- Round N+1 starts. New rule … ---`
  // before any chip / VP / hand churn from the new round.
  if (prev.phase === "resolve" && curr.phase !== "resolve") {
    const effect = prev.revealed_effect ?? curr.revealed_effect ?? null;
    const effectText = effect ? renderCard(effect, humanSeat) : null;
    const ruleSnapshot = prev.active_rule ? renderActiveRule(prev.active_rule, humanSeat) : null;
    const ruleTag = ruleSnapshot ? ` [${ruleSnapshot}]` : "";
    const tail = effectText ? ` → ${effectText}` : "";
    lines.push(`Round ${prevRound} rule${ruleTag} resolved${tail}`);
  }

  if (currRound !== prevRound) {
    const newRule = curr.active_rule ? renderActiveRule(curr.active_rule, humanSeat) : null;
    if (newRule) {
      lines.push(`--- Round ${currRound} starts. New rule: ${newRule} ---`);
    } else {
      lines.push(`--- Round ${currRound} ---`);
    }
  }

  if (prev.phase !== curr.phase) {
    lines.push(`Phase → ${(curr.phase ?? "lobby").toUpperCase()}`);
  }
  if ((prev.active_seat ?? -1) !== (curr.active_seat ?? -1) && curr.phase === "build") {
    lines.push(`Turn → ${renderSeat(curr.active_seat ?? 0, humanSeat)}`);
  }

  // Detect which slot got newly filled this broadcast (best-effort).
  const filledSlot = newlyFilledSlot(prev.active_rule, curr.active_rule);

  const burnTickSeats: number[] = [];
  const prevPlayers = new Map((prev.players ?? []).map((p) => [p.id, p] as const));

  // Goals removed from the face-up row this broadcast — used below to
  // attribute VP gains as goal claims.
  const removedGoals = collectRemovedGoals(prev.active_goals ?? [], curr.active_goals ?? []);

  for (const cp of curr.players ?? []) {
    const pp = prevPlayers.get(cp.id);
    if (!pp) continue;
    const seat = cp.seat;
    const who = renderSeat(seat, humanSeat);
    const handDelta = (cp.hand?.length ?? 0) - (pp.hand?.length ?? 0);
    const chipDelta = (cp.chips ?? 0) - (pp.chips ?? 0);
    const vpDelta = (cp.vp ?? 0) - (pp.vp ?? 0);
    const prevBurn = pp.status?.burn ?? 0;
    const currBurn = cp.status?.burn ?? 0;

    let chipsExplained = false;

    // BURN tick coalesce: at round_start, each burned player loses
    // ``BURN_TICK * prev.status.burn`` chips before any other transition.
    // Coalesce all simultaneous burn-tick chip drops into one summary line.
    if (currRound !== prevRound && prevBurn > 0 && chipDelta === -BURN_TICK * prevBurn) {
      burnTickSeats.push(seat);
      chipsExplained = true;
    }

    // Hand shrinkage: play (-1, 0 chips) vs discard (-N, -N*5 chips).
    if (handDelta < 0 && !chipsExplained && chipDelta < 0) {
      const inferredCost = -handDelta * DISCARD_COST;
      const certain = chipDelta === -inferredCost;
      const tag = certain ? "" : " ?";
      lines.push(`${who} discarded ${-handDelta} cards (cost ${-chipDelta} chips)${tag}`);
      chipsExplained = true;
    } else if (handDelta === -1 && (chipDelta === 0 || chipsExplained)) {
      if (filledSlot && filledSlot.kind === "joker" && filledSlot.card) {
        lines.push(`${who} attached ${renderCard(filledSlot.card, humanSeat)}`);
      } else if (filledSlot?.card) {
        lines.push(
          `${who} played ${renderCard(filledSlot.card, humanSeat)} into ${filledSlot.name}`,
        );
      } else if (filledSlot) {
        lines.push(`${who} played a card into ${filledSlot.name}`);
      } else {
        lines.push(`${who} played a card`);
      }
    } else if (handDelta < 0 && chipDelta === 0) {
      lines.push(`${who} lost ${-handDelta} cards`);
    } else if (handDelta > 0) {
      lines.push(`${who} drew ${handDelta} card(s)`);
    }

    if (vpDelta !== 0) {
      lines.push(vpLine(who, vpDelta, cp, removedGoals, prev, curr, humanSeat));
    }

    if (chipDelta !== 0 && !chipsExplained) {
      const sign = chipDelta > 0 ? "+" : "";
      lines.push(`${who} ${sign}${chipDelta} chips → ${cp.chips}`);
    }

    const burnDelta = currBurn - prevBurn;
    if (burnDelta > 0) {
      lines.push(`${who} BURN +${burnDelta} → ${currBurn}`);
    } else if (burnDelta < 0 && currBurn === 0) {
      lines.push(`${who} BURN cleared`);
    } else if (burnDelta < 0) {
      lines.push(`${who} BURN ${prevBurn} → ${currBurn}`);
    }

    pushStatusDiff(lines, who, pp, cp);
  }

  if (burnTickSeats.length > 0) {
    const tag = burnTickSeats.map((s) => renderSeat(s, humanSeat)).join(", ");
    lines.push(`BURN tick → ${tag}`);
  }

  if (!prev.winner && curr.winner) {
    const winnerSeat = curr.winner.seat;
    const winnerName =
      humanSeat !== null && winnerSeat === humanSeat ? "You" : `Player ${winnerSeat}`;
    lines.push(`--- WINNER: ${winnerName} ---`);
  }

  return lines;
}

interface FilledSlot {
  name: string;
  card: Card | null;
  kind: "slot" | "modifier" | "joker";
}

function newlyFilledSlot(
  prev: RuleBuilder | null | undefined,
  curr: RuleBuilder | null | undefined,
): FilledSlot | null {
  if (!curr) return null;
  const prevSlots = new Map(((prev?.slots ?? []) as Slot[]).map((s) => [s.name, s] as const));
  for (const cs of (curr.slots ?? []) as Slot[]) {
    const ps = prevSlots.get(cs.name);
    if (!ps) continue;
    if (!ps.filled_by && cs.filled_by) {
      return { name: cs.name, card: cs.filled_by, kind: "slot" };
    }
    const pMods = ps.modifiers?.length ?? 0;
    const cMods = cs.modifiers?.length ?? 0;
    if (cMods > pMods) {
      const newest = cs.modifiers?.[cMods - 1] ?? null;
      return { name: `${cs.name}+modifier`, card: newest, kind: "modifier" };
    }
  }
  // JOKER attach surfaces as ``rule.joker_attached`` rather than a slot.
  if (!prev?.joker_attached && curr.joker_attached) {
    return { name: "JOKER", card: curr.joker_attached, kind: "joker" };
  }
  return null;
}

function collectRemovedGoals(
  prev: readonly (GoalCard | null)[],
  curr: readonly (GoalCard | null)[],
): GoalCard[] {
  const out: GoalCard[] = [];
  for (let i = 0; i < Math.max(prev.length, curr.length); i++) {
    const pg = prev[i] ?? null;
    const cg = curr[i] ?? null;
    if (pg && (cg === null || cg.id !== pg.id)) out.push(pg);
  }
  return out;
}

// Heuristic: attribute a VP gain to a removed-this-broadcast goal whose
// predicate matches the player's current state, OR to a RESOLVE-phase rule
// effect, falling back to a "?" tag when neither attribution is confident.
function vpLine(
  who: string,
  vpDelta: number,
  player: Player,
  removedGoals: readonly GoalCard[],
  prev: GameState,
  curr: GameState,
  humanSeat: number | null,
): string {
  const sign = vpDelta > 0 ? "+" : "";
  const head = `${who} ${sign}${vpDelta} VP → ${player.vp}`;
  if (vpDelta <= 0) return head;

  const claimable = removedGoals.filter(
    (g) => g.vp_award === vpDelta && goalPredicateMatches(g, player, curr.round_number ?? 0),
  );
  if (claimable.length === 1) {
    return `${head} (claimed goal: ${claimable[0]?.name})`;
  }
  if (claimable.length > 1) {
    return `${head} (claimed goal: ${claimable.map((g) => g?.name).join(" | ")}) ?`;
  }

  const inResolve = prev.phase === "resolve" || curr.phase === "resolve";
  const effect = curr.revealed_effect ?? prev.revealed_effect ?? null;
  if (inResolve && effect) {
    return `${head} (rule effect: ${renderCard(effect, humanSeat)})`;
  }

  return `${head} (?)`;
}

function goalPredicateMatches(goal: GoalCard, player: Player, roundNumber: number): boolean {
  const s = player.status ?? {};
  const h = player.history ?? {};
  switch (goal.claim_condition) {
    case "chips_at_least_75":
      return (player.chips ?? 0) >= 75;
    case "chips_under_10":
      return (player.chips ?? 0) < 10;
    case "burn_at_least_2":
      return (s.burn ?? 0) >= 2;
    case "rules_completed_at_least_3":
      return ((h.rules_completed_this_game as number | undefined) ?? 0) >= 3;
    case "gifts_at_least_2":
      return ((h.cards_given_this_game as number | undefined) ?? 0) >= 2;
    case "free_agent":
      return (
        roundNumber >= 5 && (s.burn ?? 0) === 0 && !s.mute && !s.blessed && !s.marked && !s.chained
      );
    case "full_hand":
      return (player.hand?.length ?? 0) >= 7;
    default:
      // Unknown predicate — assume the goal could have been the one claimed
      // rather than falsely ruling it out. Caller still requires vp_award match.
      return true;
  }
}

function pushStatusDiff(lines: string[], who: string, prev: Player, curr: Player): void {
  const ps = prev.status ?? {};
  const cs = curr.status ?? {};
  const flags: { key: "mute" | "blessed" | "marked" | "chained"; label: string }[] = [
    { key: "mute", label: "MUTE" },
    { key: "blessed", label: "BLESSED" },
    { key: "marked", label: "MARKED" },
    { key: "chained", label: "CHAINED" },
  ];
  for (const { key, label } of flags) {
    if (!ps[key] && cs[key]) lines.push(`${who} ${label} applied`);
    else if (ps[key] && !cs[key]) lines.push(`${who} ${label} cleared`);
  }
}

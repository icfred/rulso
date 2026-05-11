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

import type { Card, GameState, Player, RuleBuilder, Slot } from "../types/envelopes";
import { renderCard } from "./cards";

const BURN_TICK = 5;
const DISCARD_COST = 5;

export function diffStates(prev: GameState, curr: GameState): string[] {
  const lines: string[] = [];

  const prevRound = prev.round_number ?? 0;
  const currRound = curr.round_number ?? 0;
  if (currRound !== prevRound) {
    lines.push(`--- Round ${currRound} ---`);
  }
  if (prev.phase !== curr.phase) {
    lines.push(`Phase → ${(curr.phase ?? "lobby").toUpperCase()}`);
  }
  if ((prev.active_seat ?? -1) !== (curr.active_seat ?? -1) && curr.phase === "build") {
    lines.push(`Turn → Player ${curr.active_seat ?? 0}`);
  }

  // Detect which slot got newly filled this broadcast (best-effort).
  const filledSlot = newlyFilledSlot(prev.active_rule, curr.active_rule);

  const burnTickSeats: number[] = [];
  const prevPlayers = new Map((prev.players ?? []).map((p) => [p.id, p] as const));

  for (const cp of curr.players ?? []) {
    const pp = prevPlayers.get(cp.id);
    if (!pp) continue;
    const seat = cp.seat;
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
      lines.push(`Player ${seat} discarded ${-handDelta} cards (cost ${-chipDelta} chips)${tag}`);
      chipsExplained = true;
    } else if (handDelta === -1 && (chipDelta === 0 || chipsExplained)) {
      const where = filledSlot ? ` into ${filledSlot.name}` : "";
      const what = filledSlot?.card ? `: ${renderCard(filledSlot.card)}` : "";
      lines.push(`Player ${seat} played a card${where}${what}`);
    } else if (handDelta < 0 && chipDelta === 0) {
      lines.push(`Player ${seat} lost ${-handDelta} cards`);
    } else if (handDelta > 0) {
      lines.push(`Player ${seat} drew ${handDelta} card(s)`);
    }

    if (vpDelta > 0) {
      lines.push(`Player ${seat} +${vpDelta} VP → ${cp.vp}`);
    } else if (vpDelta < 0) {
      lines.push(`Player ${seat} ${vpDelta} VP → ${cp.vp}`);
    }

    if (chipDelta !== 0 && !chipsExplained) {
      const sign = chipDelta > 0 ? "+" : "";
      lines.push(`Player ${seat} ${sign}${chipDelta} chips → ${cp.chips}`);
    }

    const burnDelta = currBurn - prevBurn;
    if (burnDelta > 0) {
      lines.push(`Player ${seat} BURN +${burnDelta} → ${currBurn}`);
    } else if (burnDelta < 0 && currBurn === 0) {
      lines.push(`Player ${seat} BURN cleared`);
    } else if (burnDelta < 0) {
      lines.push(`Player ${seat} BURN ${prevBurn} → ${currBurn}`);
    }

    pushStatusDiff(lines, seat, pp, cp);
  }

  if (burnTickSeats.length > 0) {
    const tag = burnTickSeats.map((s) => `Player ${s}`).join(", ");
    lines.push(`BURN tick → ${tag}`);
  }

  // Goal claim: a face-up slot loses its goal (replenished or empty).
  const prevGoals = prev.active_goals ?? [];
  const currGoals = curr.active_goals ?? [];
  for (let i = 0; i < Math.max(prevGoals.length, currGoals.length); i++) {
    const pg = prevGoals[i] ?? null;
    const cg = currGoals[i] ?? null;
    if (pg && (cg === null || cg.id !== pg.id)) {
      lines.push(`Goal claimed → ${pg.name}`);
    }
  }

  // Rule resolved: phase transitions out of RESOLVE.
  if (prev.phase === "resolve" && curr.phase !== "resolve") {
    const effect = prev.revealed_effect ?? curr.revealed_effect ?? null;
    const tail = effect ? ` → ${renderCard(effect)}` : "";
    lines.push(`Rule resolved${tail}`);
  }

  if (!prev.winner && curr.winner) {
    lines.push(`--- WINNER: Player ${curr.winner.seat} ---`);
  }

  return lines;
}

interface FilledSlot {
  name: string;
  card: Card | null;
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
      return { name: cs.name, card: cs.filled_by };
    }
    const pMods = ps.modifiers?.length ?? 0;
    const cMods = cs.modifiers?.length ?? 0;
    if (cMods > pMods) {
      const newest = cs.modifiers?.[cMods - 1] ?? null;
      return { name: `${cs.name}+modifier`, card: newest };
    }
  }
  // JOKER attach surfaces as ``rule.joker_attached`` rather than a slot.
  if (!prev?.joker_attached && curr.joker_attached) {
    return { name: "JOKER", card: curr.joker_attached };
  }
  return null;
}

function pushStatusDiff(lines: string[], seat: number, prev: Player, curr: Player): void {
  const ps = prev.status ?? {};
  const cs = curr.status ?? {};
  const flags: { key: "mute" | "blessed" | "marked" | "chained"; label: string }[] = [
    { key: "mute", label: "MUTE" },
    { key: "blessed", label: "BLESSED" },
    { key: "marked", label: "MARKED" },
    { key: "chained", label: "CHAINED" },
  ];
  for (const { key, label } of flags) {
    if (!ps[key] && cs[key]) lines.push(`Player ${seat} ${label} applied`);
    else if (ps[key] && !cs[key]) lines.push(`Player ${seat} ${label} cleared`);
  }
}

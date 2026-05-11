// Render every non-human seat's public state as one line.
//
// Floating labels are recomputed client-side (the engine never serialises
// them — see `engine/src/rulso/labels.py`). M1.5 + M2 coverage:
//   - THE LEADER  (max vp; ties → all tied)
//   - THE WOUNDED (min chips; ties → all tied)
//   - THE GENEROUS (max history.cards_given_this_game; empty if all zero)
//   - THE CURSED   (max status.burn; empty if all zero)
//   - THE MARKED   (Player.status.marked)
//   - THE CHAINED  (Player.status.chained)
// Tie-break policy follows ADR-0001: all tied players hold the label.

import type { GameState, Player } from "../types/envelopes";

type Labels = Record<string, string>;

export function renderOpponents(state: GameState, humanSeat: number): string[] {
  const labels = computeLabels(state);
  return (state.players ?? [])
    .filter((p) => p.seat !== humanSeat)
    .map((p) => renderOne(p, labels[p.id] ?? ""));
}

function renderOne(player: Player, labelSuffix: string): string {
  const labels = labelSuffix ? ` [${labelSuffix}]` : "";
  const statusText = renderStatus(player);
  const status = statusText ? `, status: ${statusText}` : "";
  return `Player ${player.seat}${labels} — chips: ${player.chips ?? 0}, VP: ${player.vp ?? 0}${status}`;
}

function renderStatus(player: Player): string {
  const s = player.status ?? {};
  const parts: string[] = [];
  const burn = s.burn ?? 0;
  if (burn > 0) parts.push(`BURN(${burn})`);
  if (s.mute) parts.push("MUTE");
  if (s.blessed) parts.push("BLESSED");
  if (s.marked) parts.push("MARKED");
  if (s.chained) parts.push("CHAINED");
  return parts.join(", ");
}

function computeLabels(state: GameState): Labels {
  const players = state.players ?? [];
  if (players.length === 0) return {};
  const out: Labels = {};
  const addLabel = (id: string, name: string): void => {
    out[id] = out[id] ? `${out[id]}, ${name}` : name;
  };

  const maxVp = Math.max(...players.map((p) => p.vp ?? 0));
  const minChips = Math.min(...players.map((p) => p.chips ?? 0));
  const maxGiven = Math.max(...players.map((p) => p.history?.cards_given_this_game ?? 0));
  const maxBurn = Math.max(...players.map((p) => p.status?.burn ?? 0));

  for (const p of players) {
    if ((p.vp ?? 0) === maxVp) addLabel(p.id, "THE LEADER");
    if ((p.chips ?? 0) === minChips) addLabel(p.id, "THE WOUNDED");
    if (maxGiven > 0 && (p.history?.cards_given_this_game ?? 0) === maxGiven) {
      addLabel(p.id, "THE GENEROUS");
    }
    if (maxBurn > 0 && (p.status?.burn ?? 0) === maxBurn) addLabel(p.id, "THE CURSED");
    if (p.status?.marked) addLabel(p.id, "THE MARKED");
    if (p.status?.chained) addLabel(p.id, "THE CHAINED");
  }
  return out;
}

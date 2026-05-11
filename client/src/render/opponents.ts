// Render every non-human seat's public state as one line.
//
// Floating-label assignments (LEADER / WOUNDED / GENEROUS / CURSED) come
// from `state.labels` on the wire — the engine publishes the canonical
// ADR-0001 computation (RUL-70). MARKED / CHAINED are status tokens and
// stay derived from `player.status` until the M2 status-apply ticket lands
// them on `state.labels`.

import type { GameState, Player } from "../types/envelopes";

export function renderOpponents(state: GameState, humanSeat: number): string[] {
  return (state.players ?? [])
    .filter((p) => p.seat !== humanSeat)
    .map((p) => renderOne(p, labelSuffix(state, p)));
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

function labelSuffix(state: GameState, player: Player): string {
  const parts: string[] = [];
  for (const [name, holders] of Object.entries(state.labels ?? {})) {
    if (holders.includes(player.id)) parts.push(name);
  }
  // Status-token labels stay client-derived until the M2 status-apply ticket
  // wires them onto `state.labels`.
  if (player.status?.marked) parts.push("THE MARKED");
  if (player.status?.chained) parts.push("THE CHAINED");
  return parts.join(", ");
}

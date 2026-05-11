// One-line header: `Round N · <PHASE> · <whose turn>`.
//
// Replaces the unanchored seat badge with a turn-aware status line so the
// playtester can see at a glance whose move the engine is waiting on. The
// connection badge (RUL-66) and seat label remain in the page header — this
// line lives just below them and is driven by `StateBroadcast.state`.

import type { GameState } from "../types/envelopes";
import { renderSeat } from "./cards";

export function renderHeader(state: GameState, humanSeat: number | null): string {
  const round = state.round_number ?? 0;
  const phase = (state.phase ?? "lobby").toUpperCase();
  if (state.winner) {
    const winnerSeat = state.winner.seat;
    const winnerName =
      humanSeat !== null && winnerSeat === humanSeat ? "You" : `Player ${winnerSeat}`;
    return `Round ${round} · END · Winner: ${winnerName}`;
  }
  if (phase === "END") {
    return `Round ${round} · END`;
  }
  const active = state.active_seat ?? 0;
  const turn =
    humanSeat !== null && active === humanSeat
      ? "Your turn"
      : `Waiting on ${renderSeat(active, humanSeat)}`;
  return `Round ${round} · ${phase} · ${turn}`;
}

// Bootstrap: connect to the engine, render every inbound envelope into the
// decision-support panels (active rule, goals, opponents) plus a collapsible
// raw-JSON log, flip the status badge as the connection lifecycle progresses,
// and render one button per legal action whenever a `StateBroadcast` carries
// a non-null `legal_actions` field. Click → `ActionSubmit` over the wire.
//
// Read-only renderer + click-to-submit input, no Pixi yet — Pixi rendering
// arrives in a later M3 sub-issue. The DOM panels live in `index.html`:
//   - #rule-preview  — `renderActiveRule(state)`
//   - #goals         — `renderGoals(state)` (one row per face-up slot)
//   - #opponents     — `renderOpponents(state, humanSeat)`
//   - #actions       — legal-action buttons (labels via `renderCard`)
//   - #app (inside <details>) — raw envelope log

import { type ConnectionStatus, connect, send } from "./net";
import { renderCard } from "./render/cards";
import { renderGoals } from "./render/goals";
import { renderOpponents } from "./render/opponents";
import { renderActiveRule } from "./render/rule";
import type {
  Card,
  DiscardRedraw,
  GameState,
  PlayCard,
  PlayJoker,
  ServerEnvelope,
  StateBroadcast,
} from "./types/envelopes";

// Wire-shape match for the inner `action` field of `ActionSubmit` — the
// generated `legal_actions` array has the same loose union (no narrowed
// `kind` discriminator). Used for log + send + label rendering.
type WireAction = PlayCard | PlayJoker | DiscardRedraw;

const DEFAULT_WS_URL = "ws://localhost:8765";

const appEl = document.getElementById("app");
const statusEl = document.getElementById("status");
const seatEl = document.getElementById("seat");
const actionsEl = document.getElementById("actions");
const ruleEl = document.getElementById("rule-preview");
const goalsEl = document.getElementById("goals");
const opponentsEl = document.getElementById("opponents");

if (!appEl || !statusEl || !seatEl || !actionsEl || !ruleEl || !goalsEl || !opponentsEl) {
  throw new Error(
    "missing #app / #status / #seat / #actions / #rule-preview / #goals / #opponents container in index.html",
  );
}

let humanSeat: number | null = null;

function setStatus(state: ConnectionStatus, detail?: string): void {
  statusEl!.dataset.state = state;
  statusEl!.textContent = detail ? `${state} · ${detail}` : state;
}

function appendEnvelope(envelope: ServerEnvelope): void {
  const block = document.createElement("pre");
  block.textContent = JSON.stringify(envelope, null, 2);
  appEl!.appendChild(block);
  block.scrollIntoView({ block: "end", behavior: "auto" });
}

function appendOutgoing(action: WireAction): void {
  const block = document.createElement("pre");
  block.classList.add("outgoing");
  block.textContent = `OUTGOING action_submit\n${JSON.stringify(action, null, 2)}`;
  appEl!.appendChild(block);
  block.scrollIntoView({ block: "end", behavior: "auto" });
}

function announceSeat(envelope: ServerEnvelope): void {
  if (envelope.type !== "hello") return;
  humanSeat = envelope.seat;
  seatEl!.textContent = `seat=${envelope.seat} · protocol=${envelope.protocol_version}`;
  // Visible in `npm run dev` console so the smoke check has a deterministic
  // line to grep for.
  console.log(`[rulso] Hello seat=${envelope.seat} protocol_version=${envelope.protocol_version}`);
}

function renderPanels(state: GameState): void {
  ruleEl!.innerHTML = "";
  ruleEl!.appendChild(panelRow("Rule", renderActiveRule(state)));

  goalsEl!.innerHTML = "";
  const goalLines = renderGoals(state);
  if (goalLines.length === 0) {
    goalsEl!.appendChild(panelRow("Goals", "(none)"));
  } else {
    for (const [index, line] of goalLines.entries()) {
      goalsEl!.appendChild(panelRow(index === 0 ? "Goals" : "", line));
    }
  }

  opponentsEl!.innerHTML = "";
  const oppLines = humanSeat !== null ? renderOpponents(state, humanSeat) : [];
  if (oppLines.length === 0) {
    opponentsEl!.appendChild(panelRow("Opponents", "(none)"));
  } else {
    for (const [index, line] of oppLines.entries()) {
      opponentsEl!.appendChild(panelRow(index === 0 ? "Opponents" : "", line));
    }
  }
}

function panelRow(label: string, text: string): HTMLElement {
  const row = document.createElement("div");
  row.classList.add("panel-row");
  const tag = document.createElement("span");
  tag.classList.add("panel-label");
  tag.textContent = label;
  row.appendChild(tag);
  const body = document.createElement("span");
  body.textContent = text;
  row.appendChild(body);
  return row;
}

// Render one button per `legal_actions[i]`. Buttons clear and rebuild on every
// `StateBroadcast`; bot-active or terminal broadcasts (`legal_actions === null`)
// leave the container empty. `ErrorEnvelope` does NOT clear the buttons —
// the human's turn (and its legal set) is still in play until the next
// `StateBroadcast` arrives.
function renderActions(broadcast: StateBroadcast, ws: WebSocket): void {
  actionsEl!.innerHTML = "";
  const legal = broadcast.legal_actions;
  if (!legal || legal.length === 0) return;
  const hand = humanHand(broadcast.state);
  for (const action of legal) {
    const btn = document.createElement("button");
    btn.type = "button";
    btn.textContent = renderActionLabel(action, hand);
    btn.addEventListener("click", () => {
      // Disable every button so a double-click doesn't submit twice. The next
      // broadcast rebuilds the list from scratch.
      for (const child of Array.from(actionsEl!.children)) {
        (child as HTMLButtonElement).disabled = true;
      }
      send(ws, { type: "action_submit", action });
      appendOutgoing(action);
    });
    actionsEl!.appendChild(btn);
  }
}

function humanHand(state: GameState): readonly Card[] {
  if (humanSeat === null) return [];
  const player = (state.players ?? []).find((p) => p.seat === humanSeat);
  return player?.hand ?? [];
}

function renderActionLabel(action: WireAction, hand: readonly Card[]): string {
  const byId = new Map(hand.map((c) => [c.id, c] as const));
  if ("slot" in action) {
    const card = byId.get(action.card_id);
    const cardText = card ? renderCard(card) : action.card_id;
    const dice = action.dice ? ` (${action.dice}d6)` : "";
    return `Play ${cardText} into ${action.slot}${dice}`;
  }
  if ("card_ids" in action) {
    const cards = action.card_ids.map((id) => {
      const card = byId.get(id);
      return card ? renderCard(card) : id;
    });
    return `Discard & redraw: ${cards.join(", ")}`;
  }
  const joker = byId.get(action.card_id);
  return `Attach ${joker ? renderCard(joker) : action.card_id}`;
}

const ws = connect(DEFAULT_WS_URL, {
  onStatus: setStatus,
  onEnvelope: (envelope) => {
    announceSeat(envelope);
    appendEnvelope(envelope);
    if (envelope.type === "state") {
      renderPanels(envelope.state);
      renderActions(envelope, ws);
    }
  },
});

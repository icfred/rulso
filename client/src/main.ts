// Bootstrap: connect to the engine, render every inbound envelope as a `<pre>`
// JSON block, flip the status badge as the connection lifecycle progresses,
// and render one button per legal action whenever a `StateBroadcast` carries
// a non-null `legal_actions` field. Click → `ActionSubmit` over the wire.
//
// Read-only renderer + click-to-submit input, no Pixi yet — Pixi rendering
// arrives in a later M3 sub-issue.

import { type ConnectionStatus, connect, send } from "./net";
import type {
  DiscardRedraw,
  PlayCard,
  PlayJoker,
  ServerEnvelope,
  StateBroadcast,
} from "./types/envelopes";

// Wire-shape match for the inner `action` field of `ActionSubmit` — the
// generated `legal_actions` array has the same loose union (no narrowed
// `kind` discriminator). Used for log + send.
type WireAction = PlayCard | PlayJoker | DiscardRedraw;

const DEFAULT_WS_URL = "ws://localhost:8765";

const appEl = document.getElementById("app");
const statusEl = document.getElementById("status");
const seatEl = document.getElementById("seat");
const actionsEl = document.getElementById("actions");

if (!appEl || !statusEl || !seatEl || !actionsEl) {
  throw new Error("missing #app / #status / #seat / #actions container in index.html");
}

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
  seatEl!.textContent = `seat=${envelope.seat} · protocol=${envelope.protocol_version}`;
  // Visible in `npm run dev` console so the smoke check has a deterministic
  // line to grep for.
  console.log(`[rulso] Hello seat=${envelope.seat} protocol_version=${envelope.protocol_version}`);
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
  for (const action of legal) {
    const btn = document.createElement("button");
    btn.type = "button";
    btn.textContent = JSON.stringify(action);
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

const ws = connect(DEFAULT_WS_URL, {
  onStatus: setStatus,
  onEnvelope: (envelope) => {
    announceSeat(envelope);
    appendEnvelope(envelope);
    if (envelope.type === "state") {
      renderActions(envelope, ws);
    }
  },
});

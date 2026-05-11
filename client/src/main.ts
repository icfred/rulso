// Bootstrap: connect to the engine, render every inbound envelope as a `<pre>`
// JSON block, flip the status badge as the connection lifecycle progresses.
//
// Read-only for RUL-66 — no input, no Pixi rendering yet. Both arrive in
// follow-up M3 sub-issues; the goal here is a tab that proves engine→client
// traffic flows through generated types without drift.

import { type ConnectionStatus, connect } from "./net";
import type { ServerEnvelope } from "./types/envelopes";

const DEFAULT_WS_URL = "ws://localhost:8765";

const appEl = document.getElementById("app");
const statusEl = document.getElementById("status");
const seatEl = document.getElementById("seat");

if (!appEl || !statusEl || !seatEl) {
  throw new Error("missing #app / #status / #seat container in index.html");
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

function announceSeat(envelope: ServerEnvelope): void {
  if (envelope.type !== "hello") return;
  seatEl!.textContent = `seat=${envelope.seat} · protocol=${envelope.protocol_version}`;
  // Visible in `npm run dev` console so the smoke check has a deterministic
  // line to grep for.
  console.log(`[rulso] Hello seat=${envelope.seat} protocol_version=${envelope.protocol_version}`);
}

connect(DEFAULT_WS_URL, {
  onStatus: setStatus,
  onEnvelope: (envelope) => {
    announceSeat(envelope);
    appendEnvelope(envelope);
  },
});

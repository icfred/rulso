// Minimal WebSocket client for the M3 foundation tab.
//
// Opens one connection to the engine's `rulso-server` (default ws://localhost:8765),
// parses inbound JSON via the generated `ServerEnvelope` union, and dispatches
// each envelope to a callback. `send` serialises a `ClientEnvelope` (e.g.
// `ActionSubmit`) onto the same connection — used by the input layer to
// submit the human's chosen action (RUL-67).

import type { ClientEnvelope, ServerEnvelope } from "./types/envelopes";

export type ConnectionStatus = "connecting" | "connected" | "closed" | "error";

export interface NetHandlers {
  onEnvelope: (envelope: ServerEnvelope) => void;
  onStatus: (status: ConnectionStatus, detail?: string) => void;
}

export function connect(url: string, handlers: NetHandlers): WebSocket {
  handlers.onStatus("connecting");
  const ws = new WebSocket(url);

  ws.addEventListener("open", () => {
    handlers.onStatus("connected");
  });

  ws.addEventListener("message", (event) => {
    const raw = typeof event.data === "string" ? event.data : "";
    if (!raw) return;
    const envelope = parseEnvelope(raw);
    if (envelope === null) {
      handlers.onStatus("error", `unparseable envelope: ${raw.slice(0, 120)}`);
      return;
    }
    handlers.onEnvelope(envelope);
  });

  ws.addEventListener("close", (event) => {
    handlers.onStatus("closed", `code=${event.code} reason=${event.reason || "—"}`);
  });

  ws.addEventListener("error", () => {
    handlers.onStatus("error", "websocket error");
  });

  return ws;
}

// Serialise a `ClientEnvelope` and send it on the open connection. The engine
// re-validates structurally and re-checks legality on receipt; we type-check
// the envelope shape here so the compiler catches drift between the generated
// types and the call site.
export function send(ws: WebSocket, envelope: ClientEnvelope): void {
  ws.send(JSON.stringify(envelope));
}

// Narrow an inbound JSON string to a `ServerEnvelope`. Returns `null` on JSON
// parse failure or when the `type` discriminator is missing/unknown. The
// engine is authoritative on shape; we only validate the discriminator and
// hand the rest through unchanged for the renderer to inspect.
export function parseEnvelope(raw: string): ServerEnvelope | null {
  let parsed: unknown;
  try {
    parsed = JSON.parse(raw);
  } catch {
    return null;
  }
  if (parsed === null || typeof parsed !== "object") return null;
  const candidate = parsed as { type?: unknown };
  if (candidate.type !== "hello" && candidate.type !== "state" && candidate.type !== "error") {
    return null;
  }
  return parsed as ServerEnvelope;
}

// Bootstrap: open the WebSocket, render every inbound envelope across the
// decision-support panels (header / transcript / you / rule / goals /
// opponents / actions), and submit one `ActionSubmit` per user click.
//
// RUL-72 reshape:
// - Header (NEW): `Round N · <PHASE> · <whose turn>` driven by every state push.
// - Transcript (NEW): consecutive `StateBroadcast`s diffed into a coarse log;
//   replaces the hidden raw JSON `<details>`.
// - You panel (NEW): the human's seat + hand as a typed card list.
// - Rule / Goals / Opponents: enriched per the RUL-72 hand-over.
// - Actions: grouped by slot; discard uses a card-toggle UI instead of a flat
//   button per legal subset.
//
// Discard selection state lives here (the controller), keyed to one
// `StateBroadcast`. Every fresh broadcast clears the selection so the user
// starts from a known empty state each turn.

import { type ConnectionStatus, connect, send } from "./net";
import { renderActions } from "./render/actions";
import { renderCard } from "./render/cards";
import { renderGoals } from "./render/goals";
import { renderHeader } from "./render/header";
import { renderOpponents } from "./render/opponents";
import { renderRulePanel } from "./render/rule";
import { diffStates } from "./render/transcript";
import { renderYou } from "./render/you";
import type {
  Card,
  DiscardRedraw,
  GameState,
  PlayCard,
  PlayJoker,
  ServerEnvelope,
  StateBroadcast,
} from "./types/envelopes";

type WireAction = PlayCard | PlayJoker | DiscardRedraw;

const DEFAULT_WS_URL = "ws://localhost:8765";

const statusEl = document.getElementById("status");
const seatEl = document.getElementById("seat");
const headerEl = document.getElementById("header-line");
const transcriptEl = document.getElementById("transcript");
const youEl = document.getElementById("you");
const ruleEl = document.getElementById("rule-preview");
const goalsEl = document.getElementById("goals");
const opponentsEl = document.getElementById("opponents");
const actionsEl = document.getElementById("actions");

if (
  !statusEl ||
  !seatEl ||
  !headerEl ||
  !transcriptEl ||
  !youEl ||
  !ruleEl ||
  !goalsEl ||
  !opponentsEl ||
  !actionsEl
) {
  throw new Error(
    "missing #status / #seat / #header-line / #transcript / #you / #rule-preview / #goals / #opponents / #actions container in index.html",
  );
}

interface AppState {
  humanSeat: number | null;
  lastState: GameState | null;
  discardSelection: Set<string>;
}

const app: AppState = {
  humanSeat: null,
  lastState: null,
  discardSelection: new Set(),
};

function setStatus(state: ConnectionStatus, detail?: string): void {
  statusEl!.dataset.state = state;
  statusEl!.textContent = detail ? `${state} · ${detail}` : state;
}

function announceSeat(envelope: ServerEnvelope): void {
  if (envelope.type !== "hello") return;
  app.humanSeat = envelope.seat;
  seatEl!.textContent = `seat=${envelope.seat} · protocol=${envelope.protocol_version}`;
  console.log(`[rulso] Hello seat=${envelope.seat} protocol_version=${envelope.protocol_version}`);
}

function appendTranscript(lines: readonly string[], cls?: string): void {
  for (const text of lines) {
    const row = document.createElement("div");
    row.classList.add("transcript-line");
    if (cls) row.classList.add(cls);
    row.textContent = text;
    transcriptEl!.appendChild(row);
  }
  transcriptEl!.scrollTop = transcriptEl!.scrollHeight;
}

function ingestBroadcast(broadcast: StateBroadcast): void {
  const state = broadcast.state;
  const prior = app.lastState;
  if (prior) {
    const lines = diffStates(prior, state, app.humanSeat);
    if (lines.length > 0) appendTranscript(lines);
  } else {
    appendTranscript([
      `--- Connected · Round ${state.round_number ?? 0} · ${(state.phase ?? "lobby").toUpperCase()} ---`,
    ]);
  }
  app.lastState = state;
  app.discardSelection.clear();
  renderAll(broadcast);
}

function renderAll(broadcast: StateBroadcast): void {
  const state = broadcast.state;

  headerEl!.textContent = renderHeader(state, app.humanSeat);

  ruleEl!.innerHTML = "";
  for (const line of renderRulePanel(state, app.humanSeat)) {
    ruleEl!.appendChild(panelRowText(line.text));
  }

  goalsEl!.innerHTML = "";
  const goalLines = renderGoals(state);
  if (goalLines.length === 0) {
    goalsEl!.appendChild(panelRowText("(no goals)"));
  } else {
    for (const line of goalLines) {
      const row = panelRowText(line.text);
      if (line.indent) row.classList.add("panel-indent");
      goalsEl!.appendChild(row);
    }
  }

  youEl!.innerHTML = "";
  if (app.humanSeat !== null) {
    for (const line of renderYou(state, app.humanSeat)) {
      youEl!.appendChild(panelRowText(line.text));
    }
  } else {
    youEl!.appendChild(panelRowText("(awaiting Hello)"));
  }

  opponentsEl!.innerHTML = "";
  const oppLines = app.humanSeat !== null ? renderOpponents(state, app.humanSeat) : [];
  if (oppLines.length === 0) {
    opponentsEl!.appendChild(panelRowText("(no opponents)"));
  } else {
    for (const line of oppLines) {
      opponentsEl!.appendChild(panelRowText(line));
    }
  }

  renderActions(
    actionsEl!,
    broadcast.legal_actions ?? null,
    state,
    app.humanSeat,
    {
      selection: app.discardSelection,
      onToggle: (cardId) => {
        if (app.discardSelection.has(cardId)) app.discardSelection.delete(cardId);
        else app.discardSelection.add(cardId);
        renderAll(broadcast);
      },
    },
    {
      onPlay: (action) => submitAction(action, broadcast),
      onDiscard: (action) => submitAction(action, broadcast),
    },
  );
}

function submitAction(action: WireAction, broadcast: StateBroadcast): void {
  disableActions();
  send(ws, { type: "action_submit", action });
  appendTranscript([describeOwnAction(action, broadcast.state)], "transcript-own");
}

function disableActions(): void {
  for (const el of Array.from(actionsEl!.querySelectorAll("button"))) {
    (el as HTMLButtonElement).disabled = true;
  }
}

function describeOwnAction(action: WireAction, state: GameState): string {
  const hand = handFor(state, app.humanSeat);
  const byId = new Map(hand.map((c) => [c.id, c] as const));
  if ("slot" in action) {
    const card = byId.get(action.card_id);
    const cardText = card ? renderCard(card, app.humanSeat) : "card";
    const dice = action.dice ? ` (${action.dice}d6)` : "";
    return `→ You played ${cardText} into ${action.slot}${dice}`;
  }
  if ("card_ids" in action) {
    const cost = action.card_ids.length * 5;
    return `→ You discarded ${action.card_ids.length} card(s) (cost ${cost} chips)`;
  }
  const joker = byId.get(action.card_id);
  return `→ You attached ${joker ? renderCard(joker, app.humanSeat) : "JOKER"}`;
}

function handFor(state: GameState, humanSeat: number | null): readonly Card[] {
  if (humanSeat === null) return [];
  return (state.players ?? []).find((p) => p.seat === humanSeat)?.hand ?? [];
}

function panelRowText(text: string): HTMLElement {
  const row = document.createElement("div");
  row.classList.add("panel-row");
  row.textContent = text;
  return row;
}

const ws = connect(DEFAULT_WS_URL, {
  onStatus: setStatus,
  onEnvelope: (envelope) => {
    announceSeat(envelope);
    if (envelope.type === "state") {
      ingestBroadcast(envelope);
    } else if (envelope.type === "error") {
      appendTranscript(
        [`! engine error: ${envelope.code} — ${envelope.message}`],
        "transcript-error",
      );
    }
  },
});

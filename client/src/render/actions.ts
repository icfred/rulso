// Render the legal-action panel.
//
// Replaces the RUL-67 flat list of buttons (one per legal action) with three
// sections so the playtester can map cards to slots without scanning a 50+
// button explosion:
//
// 1. **Play X into <slot>** — one button per `PlayCard` action, grouped by
//    the slot the engine emitted. Comparator MODIFIERs land under the QUANT
//    slot with a dice-mode suffix (1d6 / 2d6); operator MODIFIERs land under
//    the slot they augment.
// 2. **Attach JOKER** — one button per `PlayJoker` action.
// 3. **Discard & redraw** — a card-toggle chip per hand entry that appears in
//    any `DiscardRedraw.card_ids`; click toggles `.selected` on the chip and
//    updates a live cost line; one Submit button at the bottom builds a single
//    `DiscardRedraw` from the marked subset. No modal, no drag, no separate
//    confirmation pass.
//
// Submit-once safety: the moment the user clicks any button, every clickable
// in the panel is disabled until the next `StateBroadcast` arrives — the
// caller (main.ts) blanks and re-renders the panel from scratch on each
// broadcast, so disabling locally is enough.
//
// Discard selection lifecycle: lives in the caller's controller state (the
// `DiscardController` interface below). On every fresh `StateBroadcast` the
// caller must clear it; this renderer never mutates received state.

import type { Card, DiscardRedraw, GameState, PlayCard, PlayJoker } from "../types/envelopes";
import { renderCard } from "./cards";

type WireAction = PlayCard | PlayJoker | DiscardRedraw;

const DISCARD_COST_PER_CARD = 5;
const MAX_DISCARD = 3;

export interface DiscardController {
  selection: Set<string>;
  onToggle(cardId: string): void;
}

export interface ActionHandlers {
  onPlay(action: PlayCard | PlayJoker): void;
  onDiscard(action: DiscardRedraw): void;
}

export function renderActions(
  container: HTMLElement,
  legal: readonly WireAction[] | null,
  state: GameState,
  humanSeat: number | null,
  discard: DiscardController,
  handlers: ActionHandlers,
): void {
  container.innerHTML = "";
  if (!legal || legal.length === 0) return;

  const hand = handFor(state, humanSeat);
  const byId = new Map(hand.map((c) => [c.id, c] as const));

  const playActions: PlayCard[] = [];
  const jokerActions: PlayJoker[] = [];
  const discardActions: DiscardRedraw[] = [];
  for (const action of legal) {
    if ("slot" in action) playActions.push(action);
    else if ("card_ids" in action) discardActions.push(action);
    else jokerActions.push(action);
  }

  if (playActions.length > 0) {
    const grouped = groupBySlot(playActions);
    for (const [slot, actions] of grouped) {
      container.appendChild(sectionHeader(`Fill ${slot}:`));
      const row = buttonRow();
      for (const action of actions) {
        row.appendChild(playButton(action, byId, humanSeat, handlers));
      }
      container.appendChild(row);
    }
  }

  if (jokerActions.length > 0) {
    container.appendChild(sectionHeader("Attach JOKER:"));
    const row = buttonRow();
    for (const action of jokerActions) {
      row.appendChild(jokerButton(action, byId, humanSeat, handlers));
    }
    container.appendChild(row);
  }

  if (discardActions.length > 0) {
    container.appendChild(sectionHeader("Discard & redraw:"));
    renderDiscardSection(container, discardActions, hand, humanSeat, discard, handlers);
  }
}

function handFor(state: GameState, humanSeat: number | null): readonly Card[] {
  if (humanSeat === null) return [];
  return (state.players ?? []).find((p) => p.seat === humanSeat)?.hand ?? [];
}

function groupBySlot(actions: readonly PlayCard[]): Map<string, PlayCard[]> {
  const out = new Map<string, PlayCard[]>();
  for (const action of actions) {
    const bucket = out.get(action.slot);
    if (bucket) bucket.push(action);
    else out.set(action.slot, [action]);
  }
  return out;
}

function playButton(
  action: PlayCard,
  byId: Map<string, Card>,
  humanSeat: number | null,
  handlers: ActionHandlers,
): HTMLButtonElement {
  const card = byId.get(action.card_id);
  const cardText = card ? renderCard(card, humanSeat) : "card";
  const dice = action.dice ? ` (${action.dice}d6)` : "";
  return makeButton(`${cardText}${dice}`, () => handlers.onPlay(action));
}

function jokerButton(
  action: PlayJoker,
  byId: Map<string, Card>,
  humanSeat: number | null,
  handlers: ActionHandlers,
): HTMLButtonElement {
  const card = byId.get(action.card_id);
  return makeButton(card ? renderCard(card, humanSeat) : "JOKER", () => handlers.onPlay(action));
}

function renderDiscardSection(
  container: HTMLElement,
  legal: readonly DiscardRedraw[],
  hand: readonly Card[],
  humanSeat: number | null,
  discard: DiscardController,
  handlers: ActionHandlers,
): void {
  // Build the set of discardable card ids — every card_id that appears in any
  // legal DiscardRedraw action. The engine's legality module emits subsets of
  // sizes 1..max_k drawn from the hand; for our purposes "appears anywhere"
  // means "user is allowed to mark this card for discard".
  const discardable = new Set<string>();
  for (const action of legal) {
    for (const id of action.card_ids) discardable.add(id);
  }

  const chips = document.createElement("div");
  chips.classList.add("discard-chips");
  for (const card of hand) {
    if (!discardable.has(card.id)) continue;
    const chip = document.createElement("button");
    chip.type = "button";
    chip.classList.add("discard-chip");
    if (discard.selection.has(card.id)) chip.classList.add("selected");
    chip.dataset.cardId = card.id;
    chip.textContent = `${renderCard(card, humanSeat)} [${card.type}]`;
    chip.addEventListener("click", () => discard.onToggle(card.id));
    chips.appendChild(chip);
  }
  container.appendChild(chips);

  // Submit order MUST match `itertools.combinations(player.hand, k)` —
  // ``DiscardRedraw.card_ids`` is a tuple, and the engine's legality check
  // is ``envelope.action in legal`` (order-sensitive). Build the selected
  // list by walking the hand left-to-right.
  const selected = hand
    .map((c) => c.id)
    .filter((id) => discardable.has(id) && discard.selection.has(id));
  const count = selected.length;
  const cost = count * DISCARD_COST_PER_CARD;
  const counter = document.createElement("div");
  counter.classList.add("discard-counter");
  if (count === 0) {
    counter.textContent = "Click cards above to mark them for discard.";
  } else {
    counter.textContent = `Discarding ${count} card(s) (cost ${cost} chips)`;
  }
  container.appendChild(counter);

  const submit = document.createElement("button");
  submit.type = "button";
  submit.classList.add("discard-submit");
  submit.textContent = "Submit discard";
  const within = count >= 1 && count <= MAX_DISCARD;
  const legalKey = new Set(legal.map((a) => a.card_ids.join("|")));
  const selectedKey = selected.join("|");
  const submittable = within && legalKey.has(selectedKey);
  submit.disabled = !submittable;
  if (submittable) {
    submit.addEventListener("click", () => {
      const action: DiscardRedraw = { kind: "discard_redraw", card_ids: selected };
      handlers.onDiscard(action);
    });
  }
  container.appendChild(submit);
}

function sectionHeader(text: string): HTMLElement {
  const el = document.createElement("div");
  el.classList.add("action-section-header");
  el.textContent = text;
  return el;
}

function buttonRow(): HTMLElement {
  const el = document.createElement("div");
  el.classList.add("action-row");
  return el;
}

function makeButton(label: string, onClick: () => void): HTMLButtonElement {
  const btn = document.createElement("button");
  btn.type = "button";
  btn.classList.add("action-button");
  btn.textContent = label;
  btn.addEventListener("click", () => {
    onClick();
  });
  return btn;
}

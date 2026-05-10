# Rulso

Rulso is a card game where the rules are made up as you play.

Each round the game announces an effect — *"lose 10 chips"*, *"gain 3 chips"*, *"take a burn"*. Then the players take turns adding to a sentence that decides **who** the effect hits.

One plays `IF EACH PLAYER`. The next adds `HAS LESS THAN`. Another rolls a die and adds the number. The last adds `CHIPS`. The rule reads:

> **IF EACH PLAYER HAS LESS THAN 20 CHIPS, LOSE 10 CHIPS.**

Anyone who fits, gets hit.

## The twist

Each player only adds one piece. You can't write the rule alone — you're shaping it together, and everyone wants it to land on someone *else*. Each play is a small negotiation: I want the threshold high, she wants it low, he wants it to be about red cards because his hand is mostly black.

What people add is half the game. Plays leak information about their hand, their plans, their angle.

## How rules behave

- Most rules fire and disappear.
- Some rules sit on the table, waiting for their condition to come true.
- A rare card called a **Joker** can lock a rule down so it stays around like a law of physics.

When a rule needs a number, the player rolls dice — and chooses one or two. One die is bouncier; two dice are bigger and tighter. The choice is yours.

## Winning

Public goal cards sit face-up: *"first to 100 chips"*, *"apply the third burn"*, *"build a six-word rule as dealer"*. Meet a goal, score a victory point. First to three points wins.

## What you carry

- A hand of seven cards
- A stack of chips (currency, scoreboard, and bargaining chip in one)
- Status tokens that come and go: burning, blessed, muted, marked
- Floating titles — *The Leader*, *The Wounded*, *The Cursed* — that drift between players as the game shifts

## In one line

A card game about writing rules together that never quite go where you wanted.

## Try it

The M2 engine plays a four-bot game and narrates each round to stdout. From the repo root:

```bash
uv sync --project engine
uv run --project engine rulso --seed 5 --rounds 100
```

Seed 5 reaches a winner in 14 rounds and surfaces most of the M2 vocabulary: `ANYONE` / `EACH_PLAYER` scoping, the floating `THE LEADER` / `THE WOUNDED` labels, OP-only comparator MODIFIERs with dice rolls, and a goal-claim chain that hands `p3` the deciding VP. Try a few seeds — some end with a winner (one of the bots reaches `VP_TO_WIN`); others hit the round cap because the dealer's opening hand has no `SUBJECT` card and the rule fails before anyone else gets to play. Both endings are expected M2 variance — the bots are deliberately near-random while the substrate is being locked in. M3 ISMCTS will tighten the bimodal winner split.

Want to play a hand yourself before the smart bots land? Take one of the four seats and let random bots fill the rest:

```bash
uv run --project engine rulso --seed 0 --human-seat 0
```

Each of your turns prints your hand, the in-progress rule, your status, and a numbered menu of legal actions. Type the index and press Enter; bad input is rejected without crashing.

(Either form above also works without the `--project engine` flag if you `cd engine` first. The repo has no top-level `pyproject.toml`; the `rulso` script is registered only in `engine/`.)


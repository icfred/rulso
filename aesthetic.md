# Rulso — Aesthetic

Cool, computer-y, restrained. The game *evaluates* rules; the visual language reflects that without being cold or sterile.

## Vibe

> *Modern minimal layout, pixel-art glyphs, mainframe palette.*

The rule under construction is the hero of the screen. Everything else recedes. Pixel art carries small details (status icons, dice faces, card edges); type carries the rule's words and the live grammar update.

Reference touchstones:
- *Balatro* — pixel + dense game-state UI **(touchstone only — don't clone the warm arcade vibe)**
- *Slay the Spire* — clear card text on dark, generous spacing
- *Loop Hero* — pixel + minimalist HUD

## Palette — Aegean

| Role | Hex | Usage |
|---|---|---|
| Background | `#0d1626` | Table base |
| Surface | `#172238` | Card body, panel base |
| Primary | `#a3c8e8` | Body text, default UI |
| Secondary | `#5b8cb5` | Subdued labels, inactive elements |
| Accent | `#67e8c1` | Successful resolution, slot fill, your turn |
| Warning | `#ffae3c` | "You're being targeted" / status warnings |
| Danger | `#e87a87` | Damage, illegal action feedback |

Dark-only for MVP. No light mode.

## Typography

- **Rule text**: monospace — *JetBrains Mono*. Lets letters align column-wise as the rule builds.
- **Chrome / UI**: sans — *Inter*. Clean, neutral, readable at small sizes.
- **Numbers** (chips, VP, dice): monospace, fixed-width, slightly heavier weight.

Rule text size scales as the rule grows so it always fits the active rule area.

## Layout principles

```
┌───────────────────────────────────────────────────┐
│  PERSISTENT RULES                  ACTIVE GOALS   │
├───────────────────────────────────────────────────┤
│                                                   │
│       OPPONENT 2 (top)                            │
│                                                   │
│   OPPONENT 1                  OPPONENT 3          │
│   (left)         ACTIVE RULE  (right)             │
│                  ┌─────────┐                      │
│                  │  IF X…  │                      │
│                  └─────────┘                      │
│                  EFFECT CARD                      │
│                                                   │
│       YOUR HAND (bottom, 7 cards)                 │
│       YOUR CHIPS / VP / DICE / STATUS             │
└───────────────────────────────────────────────────┘
```

Opponents are compact panels: avatar slot, chip count, VP, status icons. The active rule sits at center, large, watchable.

## Animation

- **Timing**: 180–240ms entrances/exits, 80ms hover snaps
- **Curves**: ease-out for entrances; ease-in-out for re-arranges; subtle spring on slot-fill (~250ms with one settle)
- **Style**: smooth and snappy. No bounciness. Mechanical but not stiff.
- **Card play**: lift → arc → slot, ~220ms total, with a tiny shake-equivalent on the receiving slot
- **Rule resolution**: rule text holds for ~500ms before applying effects, giving the moment its weight
- **Dice roll**: ~500ms tumble with chiptune clatter, settle on face

## Sound

Code-generated, Web Audio API. Bleep/bloop family, deliberately low-fi.

| Event | Sound |
|---|---|
| Card pickup / play | Short downward sine chirp |
| Slot fill | Rising 3-note arpeggio |
| Dice roll | White noise burst, tonal settle |
| Rule resolve (positive) | Rising major triad |
| Rule resolve (negative) | Descending diminished |
| VP claimed | Longer flourish |
| Status applied | Single sharp tone keyed to status (BURN = high buzz, BLESSED = soft ding) |

Mute and volume controls in MVP.

## Iconography

16×16 pixel glyphs, solid silhouettes, single accent color per icon for state.

| Token | Glyph |
|---|---|
| BURN | Flame |
| MUTE | Slashed circle |
| BLESSED | Halo / aura |
| MARKED | Crosshair |
| CHAINED | Chain link |

Labels use small typographic badges, not icons (they're titles, not states).

## Pixel grid

- Base unit: 16px logical, rendered 2× = 32px screen
- Cards: 80×112 logical → 160×224 rendered
- Spacing snaps to 8px or 16px increments
- No sub-pixel positioning

## Don't / avoid

- Saturated reds and golds (Balatro signature — would dilute the cool feel)
- Painterly illustration (wrong fidelity for our pixel direction)
- Comic / quirky tone (game is wry, not silly)
- Talking-narrator voice (game is silent)
- Light mode for MVP

## Open

- Final card border treatment (rounded vs hard corners)
- Sprite source — primitive shapes for M1–M3, custom or commissioned at M5
- Sound credits / palette — code-generated initially, possibly augmented with samples in polish

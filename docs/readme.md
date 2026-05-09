# docs/

Agent-curated, AI-optimized feature documentation.

## Layout

```
docs/
├── <area>/
│   ├── readme.md           # surface area, key files, public interfaces
│   └── <subfeature>.md     # one file per non-trivial subsystem
```

Areas mirror Linear projects: `engine/`, `client/`, `bots/`, `design/`, `infra/`.

## Conventions

- **Concise.** No marketing copy, no tutorials, no narratives. Dense info.
- **Updated by agents** at the end of each ticket — see `workflows/feature-work.md` steps 9–10.
- **Reference the design contract.** Don't restate `design/state.md`; link to it.
- **File paths and function names**, not paraphrased prose.
- **Why-decisions** go in commit messages, not docs.
- **Last-edited line** at the top of each file: `_Last edited: YYYY-MM-DD by RUL-<id>_`

## When to add a new sub-feature doc

- A new subsystem with its own state and entry point
- A non-trivial mechanism that other code references
- A protocol, schema, or convention that crosses files

## When NOT to

- Per-function docstring content (lives in code)
- Setup or env instructions (live in `tech.md` or area readme)
- Design rationale (lives in `design/` or commit messages)
- Roadmap status (lives in Linear)

## Distinction from `design/`

| | `design/` | `docs/` |
|---|---|---|
| Author | Human + agents on explicit design tasks | Agents during implementation |
| Stability | Stable contract; PRs that change it need user approval | Updated every ticket |
| Content | Game design, state machine, card schema | Implementation surface area, function references |

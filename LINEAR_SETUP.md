# Linear workspace setup — one-time checklist

Linear MCP wasn't surfaced in the session that scaffolded this repo, so the workspace setup needs to happen manually (or in a session where the Linear MCP is loaded). This file is the checklist; delete it once setup is complete.

## Workspace

- Workspace name: `Rulso`
- Team prefix: `RUL` (used in branch names, commit messages, and ticket IDs throughout the repo)

## Projects (= areas)

Create these as Linear **Projects**, one per area. Tickets live inside them.

| Project | Scope |
|---|---|
| Engine | Python game engine, state machine, grammar resolver, server |
| Client | TypeScript/Pixi browser client, UI, sound |
| Bots | Random and ISMCTS bots; bot evaluation harnesses |
| Design | `design/state.md`, `design/cards.yaml`, grammar specs, mechanic design |
| Infra | Repo, CI, scripts, type generation, build tooling, hooks |

## Workflow states

Linear's defaults work; just confirm the team workflow includes these states in this order:

```
Backlog → Todo (== Ready) → In Progress → In Review → Done → Cancelled
```

If the default labels are different (e.g., `Todo` instead of `Ready`), update `workflows/*.md` references to match — *or* rename the Linear state to `Ready`. Don't fight it.

## Labels

Create these labels at the workspace level (apply across all projects):

**Type**
- `feature` — new functionality
- `chore` — refactor, cleanup, dependency updates
- `bug` — fixing a defect
- `docs` — documentation-only changes

**Parallelization**
- `parallel-safe` — orchestrator may dispatch alongside other parallel-safe tickets
- `parallel-blocked` — must run serially (touches shared interfaces or has unsynced deps)

No `area:*` labels — projects already provide that axis.

## Issue conventions

- **Parent issue** = milestone (e.g., "M1: Engine core"). Lives in the relevant Project.
- **Sub-issue** = task. Always under a parent milestone issue.
- **Definition of done** lives in the issue description as a checklist of 3–6 testable bullets.
- **Dependencies** expressed as Linear "Blocked by" / "Blocks" relations between issues.

## GitHub integration

In Linear → Settings → Integrations → GitHub, connect the `<your-org-or-username>/rulso` repository. This auto-links commits and PRs that reference `RUL-<id>` to their tickets.

## When MCP is available

Once a Claude Code session has Linear MCP tools, the orchestrator can:
- Read this file
- Verify or create the Projects, labels, and states above
- Begin decomposing milestones from `roadmap.md` into tickets

Until then, set up the workspace manually via the Linear UI — it's a 5-minute job.

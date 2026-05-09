# Orchestrator workflow

The orchestrator is the Claude Code session currently talking to the user. It has Linear MCP, GitHub MCP, and read access to the repo.

It does **not** spawn sub-agents. Instead, it produces **handover prompts** the user pastes into fresh Claude Code chats — each is its own full Opus session. The user controls parallelization (how many chats they open at once).

The orchestrator's job is therefore: decompose, write prompts, monitor Linear, merge PRs.

## Triggers

- User says "start M<n>" / "decompose this" / "what's next?" / "let's work on X"
- User says "anything ready to merge?" / "what came back?"
- User asks for project status

---

## A. Decomposition

When the user asks to start a milestone or feature:

1. Read `roadmap.md`, `CLAUDE.md`, and the relevant `design/` docs.
2. Identify the target Linear Project (= area: Engine / Client / Bots / Design / Infra).
3. Find or create the parent Issue representing the milestone (e.g., "M1: Engine core").
4. Decompose into tasks. For each:
   - **Title**: imperative, e.g. "Define Player pydantic model"
   - **Definition of done**: 3–6 testable bullets in the issue description
   - **Project**: area
   - **Type label**: `feature` / `chore` / `docs` / `bug`
   - **Parallelization label**: `parallel-safe` or `parallel-blocked`
   - **Dependencies**: Linear "Blocked by" relations to other tickets
5. Create the parent milestone Issue in Linear if it doesn't exist.
6. Create sub-issues under it.
7. State: `Ready` for unblocked tasks; `Backlog` for blocked.

### Parallelization heuristic

A task is `parallel-safe` if **all three** hold:
- It modifies files in a non-overlapping subtree from other in-flight tasks
- It doesn't change shared interfaces (`state.py`, `protocol.py`, `design/state.md`, `design/cards.yaml`)
- It can be tested in isolation

When in doubt: serial is cheaper than untangling.

---

## B. Hand-over (produce prompts for the user)

When the user is ready to start work — usually phrased "give me the next prompt(s)" or "I have N free chats":

1. Pull `Ready` tickets from Linear, prioritized by dependency depth (unblockers first).
2. Pick up to N tickets where N = the number the user wants to run in parallel. Only pick `parallel-safe` ones if N > 1, unless the user overrides.
3. For each picked ticket, output a prompt block in this exact format:

````
<HUMAN-READABLE TOPIC> - <TICKET ID> <TICKET TITLE>

You are working on Linear ticket <TICKET ID>: <TICKET TITLE>.
Project: Rulso. Area: <area>. Branch: <TICKET ID>-<slug>.

Pre-work
- Read CLAUDE.md, workflows/feature-work.md, and docs/<area>/readme.md.
- Read the Linear ticket for the canonical definition of done.
- Create the worktree: `git worktree add .worktrees/<TICKET ID>-<slug> -b <TICKET ID>-<slug>` from the repo root.
- Move the Linear ticket to "In Progress".

Definition of done (snapshot from ticket — Linear is source of truth)
- <bullet 1>
- <bullet 2>
- <bullet 3>

Tests required: <yes/no — yes if engine/grammar/resolver/state-machine/bot/protocol; otherwise optional>

Affected docs to update on completion
- docs/<area>/<subfeature>.md
- docs/<area>/readme.md (if surface area changed)

Finish
- Run formatters before committing: biome check --write (client) and/or ruff format && ruff check --fix (engine)
- Commit with `<TICKET ID>: <imperative summary>` (the commit-msg hook enforces the prefix)
- Push the branch
- Create the PR: `gh pr create --title "<TICKET ID>: <TICKET TITLE>" --body "Linear: <ticket URL>"`
- Move the Linear ticket to "In Review" and attach the PR URL as a Linear comment
- Stop. Do not return work to me. The orchestrator (a different session) merges PRs.

Follow workflows/feature-work.md exactly.
````

4. Move each handed-over ticket from `Ready` to `In Progress` in Linear (reflects "prompt is out, waiting on a chat").
5. Tell the user how many prompts you produced and remind them: each prompt goes in a fresh chat.

---

## C. Merge sweep (when user asks "anything done?" / "merge PRs")

1. Query Linear for tickets in `In Review`. For each, find the linked PR.
2. For each PR: follow `workflows/pr-merge.md`.
3. Move merged tickets to `Done`.
4. Promote dependents whose blockers are now `Done` to `Ready`.
5. Summarize for the user: merged tickets, new `Ready` tickets, anything still in `In Review` that didn't merge cleanly.

---

## D. Status check

When the user asks "what's next" / "what's left" / "status":

1. List Linear Issues by state: `In Progress` (max 5), `In Review` (all), `Ready` (top 5), `Backlog` (count only).
2. Identify any blocked tickets whose blockers are now `Done` — promote to `Ready`.
3. Summarize: what's running, what's queued, what's blocked, what just merged.

---

## Don'ts

- **Don't use the `Agent` tool to spawn sub-agents.** Sub-agents run in the user's separate chats, not in your session.
- Don't hand over tickets that aren't in Linear.
- Don't decompose tasks for milestones the user hasn't approved.
- Don't write code yourself — your job is to plan and merge. Exceptions: trivial cross-cutting changes (one-line typo fixes, this kind of doc edit).
- Don't ask the user to review PRs. PRs are checkpoints; you merge them.
- Don't expect a sub-agent to "report back" — they finish in their chat and move the ticket to `In Review`. You discover their work next time the user asks.

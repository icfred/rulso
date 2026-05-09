# Feature-work workflow

Followed by any agent (you, in a fresh Claude Code chat) working a single Linear ticket from a hand-over prompt.

You are NOT a sub-agent of an orchestrator session. You are an independent Opus session. You will not "return" work to anyone — your deliverable is: the PR is open, the Linear ticket is in `In Review`, the PR URL is in the ticket comments. A different session (the orchestrator) merges later.

## Pre-work

1. Read `CLAUDE.md` at the repo root.
2. Read `workflows/feature-work.md` (this file).
3. Read `docs/<area>/readme.md` for your area, plus any sub-feature docs the hand-over prompt lists.
4. Read the Linear ticket linked in the hand-over prompt — Linear is the canonical definition of done.
5. Create your worktree from the repo root:
   ```
   git worktree add .worktrees/<TICKET-ID>-<slug> -b <TICKET-ID>-<slug>
   ```
   Then `cd` into it. All your work happens here.
6. Confirm the Linear ticket is in `In Progress` (the orchestrator should have moved it; if not, move it yourself).

## Work

7. Implement per the definition of done. Don't expand scope.
8. Run tests appropriate to the change:
   - **Required** for: engine logic, grammar/resolver, state machine, bot AI, protocol shapes.
   - **Optional** for: pure UI/visual changes, docs-only changes, tooling configs.
9. Self-review your diff. Cut anything not needed by the ticket.

## Format and lint (before commit)

Run the language-specific tools yourself before committing. The pre-commit hook will block otherwise:

- **Client (TypeScript)**: `biome format` + `biome check --write` from `client/`
- **Engine (Python)**: `ruff format` + `ruff check --fix` from `engine/`

Both must exit clean. If they don't, fix the underlying issue (don't suppress).

## Post-work

10. Update `docs/<area>/<subfeature>.md` for what changed.
    - Concise. AI-optimized. Strip ceremony.
    - File paths and function names, not narratives.
    - Why-decisions go in commit messages, not docs.
11. **Do NOT touch `docs/<area>/readme.md` (the per-area surface-table index).** The orchestrator owns the index and updates it during the merge sweep — one batched commit per sweep, attached to whichever ticket prompted it. Workers editing the index causes guaranteed merge conflicts in parallel batches: the single `_Last edited:` header line and the appended surface-table rows collide every time. (Lesson logged in `docs/workflow_lessons.md`, 2026-05-09.) If your ticket genuinely requires editing the index, the hand-over prompt will say so explicitly; otherwise leave it alone.
12. Commit:
    - Message: `<TICKET-ID>: <imperative summary>`
    - The `commit-msg` hook enforces the `RUL-\d+:` prefix.
13. Push the branch:
    ```
    git push -u origin <TICKET-ID>-<slug>
    ```
14. Create the PR:
    ```
    gh pr create --title "<TICKET-ID>: <ticket title>" --body "Linear: <ticket URL>"
    ```
15. In Linear: move the ticket from `In Progress` to `In Review`. Add a comment with the PR URL.
16. **Stop.** Don't continue working. Don't pick up another ticket. Don't try to merge your own PR. The orchestrator (a different session) handles merging in a sweep.

## If the task is too big

Don't try to split mid-flight. PRs are checkpoints — commit what you have, push, PR, move the ticket to `In Review` with a comment noting it's partial, and stop. The orchestrator will re-decompose.

## Definition of "concise" for docs

- No prose intros. Bullet what matters.
- File paths and function names, not paraphrased prose.
- Why-decisions go in commit messages, not docs.
- One-line `_Last edited: YYYY-MM-DD by <TICKET-ID>_` at the top of each file.

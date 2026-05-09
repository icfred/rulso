# PR-merge workflow

Followed by the orchestrator when a sub-agent returns a PR URL.

PRs in Rulso are **checkpoints**, not reviews. The goal is to merge cleanly and prevent parallel agents from clobbering each other.

## On PR notification

1. Pull the PR locally; check for merge conflicts against `main`.
1.5. **Spot-check the DoD.** Pick the most concrete bullet from the Linear ticket's Definition of Done and grep/diff for it in the PR. Green mergeability is not enough — workers (and orchestrator) have shipped PRs that satisfied the lint hook but missed the spec. If the bullet isn't there, do not merge — flag to user and decide between rework vs. accept-and-file-followup. (Lesson logged in `docs/workflow_lessons.md`, RUL-13/RUL-14.)
2. **Clean merge** path:
   - Squash-merge via `gh pr merge --squash --delete-branch`
3. **Conflict** path:
   - Pull `main`
   - Rebase the PR branch on `main` locally
   - Resolve conflicts (favor whatever aligns with `design/state.md` and existing patterns)
   - Force-push the rebased branch
   - Squash-merge via `gh pr merge --squash --delete-branch`
4. Move the Linear ticket to `Done`.
5. Check dependents — any tickets whose blockers are now all `Done`? Move them to `Ready` / `Todo`.
6. Remove the worktree:
   - `git worktree remove .worktrees/RUL-<id>-<slug>`
   - The `Agent` tool already cleans up worktrees that produced no changes; only ones with commits need manual removal.
7. **Update `docs/<area>/readme.md` (per-area surface-table index)** if the merged PR added a new module, test file, or public surface. One batched commit per sweep — bump the `_Last edited:` header line and append a row per new file. Workers don't touch this file (per `workflows/feature-work.md`); the orchestrator owns it to prevent parallel-merge conflicts. Commit message: `RUL-<id>: update <area> surface-table index` attached to whichever ticket prompted the edit (or the most recent merged ticket of the sweep).

## Don'ts

- Don't ask the user to review.
- Don't add reviewers, labels, milestones to the PR — Linear is the source of truth.
- Don't gate on CI — there is no CI in MVP.
- Don't merge a PR whose Linear ticket was never created.

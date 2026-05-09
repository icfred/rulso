# PR-merge workflow

Followed by the orchestrator when a sub-agent returns a PR URL.

PRs in Rulso are **checkpoints**, not reviews. The goal is to merge cleanly and prevent parallel agents from clobbering each other.

## On PR notification

1. Pull the PR locally; check for merge conflicts against `main`.
2. **Clean merge** path:
   - Squash-merge via `gh pr merge --squash --delete-branch`
3. **Conflict** path:
   - Pull `main`
   - Rebase the PR branch on `main` locally
   - Resolve conflicts (favor whatever aligns with `design/state.md` and existing patterns)
   - Force-push the rebased branch
   - Squash-merge via `gh pr merge --squash --delete-branch`
4. Move the Linear ticket to `Done`.
5. Check dependents — any tickets whose blockers are now all `Done`? Move them to `Ready`.
6. Remove the worktree:
   - `git worktree remove .worktrees/RUL-<id>-<slug>`
   - The `Agent` tool already cleans up worktrees that produced no changes; only ones with commits need manual removal.

## Don'ts

- Don't ask the user to review.
- Don't add reviewers, labels, milestones to the PR — Linear is the source of truth.
- Don't gate on CI — there is no CI in MVP.
- Don't merge a PR whose Linear ticket was never created.

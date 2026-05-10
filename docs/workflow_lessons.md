# Workflow Lessons

Captured workflow misses. Append-only. The improvement agent reads these in batches and proposes template updates; never auto-propagated.

Format per entry (per global protocol):

```
---
date: YYYY-MM-DD
ticket-context: TICKET-IDs
template-worthy: yes | no | maybe
---

## What happened
{one paragraph}

## Root cause
{one paragraph}

## Fix in project
{action taken or planned}

## Proposed template change
{only if template-worthy: yes/maybe}
```

---

---
date: 2026-05-09
ticket-context: RUL-13, RUL-14
template-worthy: yes
---

## What happened

RUL-13 was a chore ticket with a one-line DoD: pre-commit hook should call `ruff` via `uv run --project engine ruff …`. The worker submitted PR #2; the orchestrator squash-merged it on green mergeability without spot-checking the diff. The PR did not satisfy the DoD — the merged hook still called bare `ruff`. The failure surfaced when RUL-8's worker hit "ruff not found" and worked around it with manual `PATH=` munging. Recovery cost: PR #2 marked Done in error → ticket Canceled → new RUL-14 created → PR #5 written, rebased, force-pushed, and merged. Roughly one extra orchestrator-loop and one extra worker-session of waste.

## Root cause

The orchestrator's merge sweep treated `mergeStateStatus: CLEAN` as authoritative on the question "did this PR do its job". `CLEAN` only attests to the merge mechanics. The worker's hand-back claimed the work was done; the orchestrator did not cross-check the claim against the diff. The DoD was concrete enough (`uv run --project engine ruff`) that a 10-second `git diff origin/main..<branch> -- .githooks/pre-commit` would have caught the regression.

## Fix in project

- Memory rule saved (`feedback_pr_dod_verify.md`): before squash-merging any PR, eyeball one or two concrete DoD bullets against the diff. Applied successfully on RUL-14, RUL-8 redo, RUL-9, RUL-10, RUL-11.
- `PROJECT_CONTEXT.md` workflow conventions section now spells out: "Spot-check one DoD bullet against the diff before merging — green mergeability is not enough".

## Proposed template change

`workflows/pr-merge.md` step 2 currently reads "Squash-merge via `gh pr merge --squash --delete-branch`". Insert a step 1.5: "Spot-check: pick the most concrete DoD bullet from the Linear ticket and grep/diff for it in the PR. If it's not there, do not merge — flag to user, decide between rework vs. accept-and-file-followup." This converts a memory rule (which only this orchestrator session benefits from) into a workflow rule (which every fresh orchestrator chat picks up automatically).

---

---
date: 2026-05-09
ticket-context: RUL-7, RUL-8
template-worthy: maybe
---

## What happened

RUL-7 (state.py models) and RUL-8 (round flow phase machine) were dispatched in sequence — RUL-8's hand-over prompt was emitted after RUL-7 had merged. But the RUL-8 worker had been running concurrently in a chat opened earlier; their worktree was branched from pre-RUL-7 main. They never read the merged state.py. Instead of *adding* the state shapes they needed, they rewrote state.py from scratch with an incompatible design: `Literal` instead of `StrEnum`, `Config` class instead of module-level constants, `StatusTokens`/`SlotKind`/`CONDITION` not present in RUL-7, seat-based instead of player-id-based references. The rebase produced a cascade of conflicts. PR #4 was closed; RUL-8 was re-dispatched onto current main with explicit "ADD-ONLY edits to state.py" constraints. The redo landed cleanly with three additive lines on `GameState`.

## Root cause

Two reinforcing factors. (1) The hand-over prompt didn't *force* the worker to read post-merge state.py; it told them to read it but gave them latitude to design their own shapes when the existing ones felt incomplete. (2) The state machine ticket genuinely needed extensions to state.py (Config, build_turns_taken, etc.), and the prompt didn't enumerate them as "add these fields", which left the worker to invent their own. A worker faced with "the existing model lacks what I need" and no explicit additive-only constraint will rewrite rather than extend.

## Fix in project

- `PROJECT_CONTEXT.md` substrate watchpoints section now spells out: "engine/src/rulso/state.py is the contract. Additive-only edits — no renames, retypes, or removals. Workers who rewrite state.py from scratch get re-dispatched."
- The RUL-8 re-dispatch prompt added an explicit "Hard constraints on state.py changes" block with concrete rules (add-only, no shadowing, frozen Pydantic v2). This block is reusable for any future ticket that needs to extend a substrate file.

## Proposed template change

`workflows/orchestrator.md` section B (hand-over format) could grow an optional "Substrate constraints" block when the ticket touches a substrate file (state.py, protocol.py, etc.). Template wording lifted from the RUL-8 redo prompt:

```
Hard constraints on <substrate file> changes
- ADD-ONLY edits. Do not rename, retype, or remove existing fields.
- If you need new shapes (e.g. <list>), add them ALONGSIDE existing fields. <Pattern enforcement, e.g. "Frozen Pydantic v2 only">.
- Do not introduce parallel structures that shadow existing module-level definitions.
- All existing tests in <test file> must still pass without edits to that file.
```

The orchestrator inserts this block when `parallel-blocked` is triggered by substrate overlap. This converts the substrate-first rule from cultural knowledge into mechanical scaffolding.

---

---
date: 2026-05-09
ticket-context: RUL-12, RUL-16, RUL-19, RUL-20
template-worthy: yes
---

## What happened

In one M1.5 merge sweep (RUL-12, RUL-16, RUL-19, RUL-20 all in flight in parallel), three of the four PRs hit merge conflicts on `docs/engine/readme.md`. Each conflict cost a worktree rebase + force-push + re-merge cycle (RUL-20 conflicted with RUL-12; RUL-19 conflicted with both RUL-12 and RUL-20 cumulatively). All conflicts were on (a) the single `_Last edited: YYYY-MM-DD by RUL-N_` header line that every PR rewrites, and (b) adjacent surface-table rows added at the bottom of the same section.

## Root cause

`workflows/feature-work.md` step 11 instructs every worker to "Update `docs/<area>/readme.md` if surface area changed". The readme is the engine's surface-table index — every M1/M1.5 PR adds a module or test, so every PR touches it. When PRs run in parallel, each updates the same single-line header and appends rows in the same region; git auto-merge cannot disambiguate identical-line-position changes. The conflict is not a worker mistake — it is structurally guaranteed by the workflow rule. Workers each correctly followed the instruction and produced mutually conflicting diffs.

## Fix in project

- `workflows/feature-work.md` step 11 changed: workers add per-module doc files (`labels.md`, `cards.md`, etc.) but DO NOT touch `docs/engine/readme.md`. The orchestrator updates the surface-table index (and bumps the `_Last edited:` header) in a tiny commit during the merge sweep — one orchestrator commit per sweep, batches all new rows.
- `workflows/pr-merge.md` should grow a step: after merging the worker PR, append the new module's row to `docs/<area>/readme.md` and bump the header line. Single commit per sweep, attached to whichever ticket prompted the sweep.
- Hand-over template (`workflows/orchestrator.md`): explicit "Do not touch `docs/<area>/readme.md` index" line in the substrate-constraints block when the area's surface table would otherwise be the natural target of a worker edit.
- Memory: `feedback_merge_conflict_prevention.md` saved so future orchestrator sessions don't re-learn this from another expensive sweep.

## Proposed template change

Global `CLAUDE.md` substrate-watchpoints section could grow a generic rule: "Index docs (a single file per area whose job is to enumerate the area's surface) are orchestrator-owned. Workers add their per-module doc; the orchestrator merges the index update into the merge-sweep commit." Same shape as substrate-additive rule for `state.py` — workers don't redesign the contract; they extend it within the rules. Per-area readmes are the doc-equivalent of substrate.

---

---
date: 2026-05-09
ticket-context: RUL-19, RUL-22, RUL-23
template-worthy: yes
---

## What happened

Twice in this session, an orchestrator-authored cross-cutting commit (PR #14 = ADR-0001 ratification, PR #15 = `workflows/feature-work.md` rule fix) was tagged with a real feature ticket's `RUL-N:` prefix to satisfy the `commit-msg` hook. PR #14's `RUL-19:` prefix was harmless — RUL-19 was about to be marked Done anyway. PR #15's `RUL-22:` prefix was destructive: Linear's GitHub auto-close behaviour marked RUL-22 Done on merge, even though the actual scope-wiring code hadn't been written. Caught by spot-checking Linear after the merge; flipped RUL-22 back to Todo manually. Cost: one round of confusion, a manual status-flip, and a memory rule to ensure the next orchestrator session catches it.

## Root cause

Three reinforcing factors. (1) The `commit-msg` hook enforces `RUL-<id>: <subject>` on every commit — there's no escape hatch for orchestrator-authored cross-cutting work. (2) Linear's GitHub integration auto-closes any ticket whose `RUL-N` identifier appears in a merged PR title. (3) The orchestrator's natural instinct when picking a prefix for a meta-commit is "the ticket whose *story* this commit supports" — which is exactly the ticket Linear will then close prematurely. Three independently sensible mechanisms compose to break a real ticket's status.

## Fix in project

- New ticket `RUL-23` (`Meta — orchestrator-authored cross-cutting commits`) opened as a permanent home for orchestrator-authored commits with no feature-ticket home. Stays in `In Progress` forever; Linear auto-close lands harmlessly. Orchestrator uses `RUL-23:` for ADR ratifications, workflow-doc fixes, surface-table index updates, etc. Worker tickets keep their own prefixes — workers never use `RUL-23`.
- Memory rule `feedback_orchestrator_pr_prefix_gotcha.md` saved (2026-05-09): catches the case where a real ticket's prefix is reused, requires a manual flip-back as part of the merge sweep.
- `workflows/pr-merge.md` step 7 (added in PR #15) is the natural site to enforce the routing: "the readme-index commit attaches to RUL-23, not the most recent feature ticket".

## Proposed template change

Long-term, the cleanest fix is at the commit-msg hook itself: accept either `RUL-<id>: <subject>` OR a `meta: <subject>` / `chore: <subject>` prefix that Linear's auto-close ignores. That removes the orchestrator's need for a meta-ticket entirely. Until then, the meta-ticket workaround is fine — but every personal project using the same Linear-auto-close pattern hits this gotcha sooner or later. Worth promoting to global `CLAUDE.md`: "Open a `<PREFIX>-meta` ticket per project as the home for orchestrator-authored cross-cutting commits; reuse a real ticket's prefix only when that ticket is genuinely the originating scope."

---

---
date: 2026-05-09
ticket-context: RUL-16, RUL-17, RUL-18, RUL-22
template-worthy: yes
---

## What happened

The card-inventory spike (RUL-16) introduced two name conventions that the next worker (RUL-17, encoding `cards.yaml`) faithfully adopted: SUBJECT literal cards used `seat_0..3`; SUBJECT label cards used `LEADER` / `WOUNDED`. The existing engine, however, had `Player.id = "p0".."p3"` (set in `rules.start_game`) and `labels.LABEL_NAMES = ("THE LEADER", "THE WOUNDED", …)` (per ADR-0001 / RUL-19). The mismatch was invisible at RUL-16 merge time (a docs-only spike PR), invisible at RUL-17 implementation time (the worker correctly followed the hand-over spec which echoed the inventory doc), and only surfaced at RUL-17's handback when the worker noted the divergence in the Flags section. By that point cards.yaml was on `main` with the wrong names; reconciliation got bolted onto RUL-18's hand-over as a substrate-naming sub-task. Cost was modest — one extra paragraph in the RUL-18 brief and a small rename pass — but the divergence sat in main for ~30 minutes between RUL-17 merge and RUL-18 dispatch, and would have caused a silent runtime no-op (label SUBJECTs scoping to nothing) had it shipped to RUL-21 unfixed.

A similar pattern earlier in the same milestone: RUL-19's ticket text claimed "scoping by LEADER / WOUNDED will naturally start firing — verify this stays true — no code changes in effects.py". That was wrong; `effects._scope_subject` hard-returned `frozenset()` for label SUBJECTs. The RUL-19 worker correctly flagged it; RUL-22 was filed to wire the scoping. RUL-22 ran parallel to RUL-17 so it didn't cost wall-clock — but the orchestrator (me, in the prior turn that wrote RUL-19) should have grepped `_scope_subject` instead of trusting the ticket's own claim about downstream impact.

## Root cause

Two reinforcing factors. (1) **Spike PRs and ticket text introduce identifiers that the engine has to consume**, but those PRs/tickets have no executable check that those identifiers actually match what the engine already exposes. A docs-only PR has no failing test at merge time. (2) **The orchestrator's spot-check rule (`workflows/pr-merge.md` step 1.5) targets the PR's own DoD**, not "do the names this PR introduces match anything on the consuming side". The check that would have caught both misses is a name-cross-reference: take any new identifier the PR adds (card name, function name, status string, slot key) and grep the engine for the consuming code's expectation. That check isn't currently part of the merge sweep.

## Fix in project

- Memory rule saved (`feedback_orchestrator_data_doc_name_check.md`): when merging any spike / docs-only PR or any ticket whose deliverable is "names that downstream code will consume" (cards.yaml, protocol message types, status tokens, slot keys, label keys), grep the new names against the engine for downstream consumers and verify they match. ~1 minute per merge; saves a downstream reconciliation paragraph.
- `workflows/pr-merge.md` step 1.5 should grow a sub-bullet: "If the PR introduces identifiers (card names, label names, slot keys, message types, etc.) that downstream code will consume, grep the engine for the consuming match-site and verify alignment. Mismatch ≠ blocker; flag it before merge so the next ticket inherits the alignment task explicitly rather than discovering it at handback."
- Hand-overs for "introduces identifiers" tickets should include a "Cross-reference checklist" bullet pointing the worker at the consuming code (e.g. `effects._scope_subject` is what reads `card.name` for SUBJECTs), so workers can self-check before handback.

## Proposed template change

Global `CLAUDE.md` substrate-watchpoints / spike conventions could grow: "When a ticket's deliverable is a set of identifiers (data file, protocol shape, status tokens, slot keys), the ticket's DoD must include a cross-reference step: 'I have grepped the engine for downstream consumers of these names and confirmed they match.' Spike workers and orchestrator both verify at handback / merge." This converts a manual orchestrator habit into a ticket-template requirement, catching the divergence at the right step (when the names are first introduced) rather than at the consuming-ticket merge two PRs later.

---

---
date: 2026-05-10
ticket-context: RUL-23 (workflow fix), all worker tickets since RUL-6
template-worthy: yes
---

## What happened

The user noticed that fresh worker chats spin up worktrees on a stale base. Pattern: orchestrator merges PR #N via `gh pr merge --squash --delete-branch` → origin/main advances → local main stays at the previous tip → next worker runs `git worktree add .worktrees/X -b X` → worktree branches from local main = stale → worker writes code on a base that's missing every PR merged this session. The RUL-20 worker explicitly noticed this in their handback: "Local main was 7 commits behind origin/main; created the worktree from origin/main directly so RUL-9's resolver code was actually present." Workers since have hit it intermittently — sometimes producing merge conflicts at PR time, sometimes producing implementations that re-build something that already exists on origin.

## Root cause

Three reinforcing factors. (1) `gh pr merge` advances the remote ref but doesn't fetch + fast-forward the local checkout — that's a `git pull` step. (2) `workflows/feature-work.md` step 5 instructed workers to run `git worktree add .worktrees/X -b X` with no explicit base — git defaults the base to current HEAD = local main. (3) The orchestrator deliberately doesn't `git pull` because the user has uncommitted working-tree changes that a pull might conflict with — so local main stays stale by design. The combination produced silent staleness that was only caught when a worker happened to grep their fresh worktree for files that *should* exist (e.g. RUL-9's resolver) and didn't find them.

## Fix in project

- `workflows/feature-work.md` step 5 now mandates `git fetch origin && git worktree add ... -b <ticket> origin/main`. Workers always start from the actual remote main, regardless of local-main lag. Landed in PR #21 (RUL-23).
- Memory rule saved (`feedback_worker_worktree_base.md`) so future orchestrator chats include the fetch+origin/main step in hand-overs even before workers re-read feature-work.md.
- Orchestrator-authored commits already do this (temp worktrees branched explicitly off `origin/main`), so this is a worker-contract fix, not an orchestrator process change.

## Proposed template change

Global `CLAUDE.md` worker contract section could grow a one-liner: "Worktrees ALWAYS branch from `origin/main`, not local HEAD. Run `git fetch origin` first." This is a generic-enough invariant that it belongs in the global protocol — every personal project where the orchestrator merges PRs without pulling will hit this. Bonus: adding a tiny `make worktree` / shell helper that wraps `git fetch origin && git worktree add .worktrees/$1 -b $1 origin/main` would make it impossible to get wrong; consider per project.

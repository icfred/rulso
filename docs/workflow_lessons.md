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

---

---
date: 2026-05-10
ticket-context: RUL-31
template-worthy: yes
---

## What happened

RUL-31's DoD shipped two clauses that contradict each other under any non-trivial reading. The "cards.yaml extensions" section listed: "**deck:** composition: add per-card-kind copies for the new main-deck additions (SUBJECTs, NOUNs, MODIFIERs, JOKERs)." The "Hard constraints" section listed: "No behaviour change for M1.5 paths. `uv run rulso --seed 0` produces identical output before/after." Any deck change reshuffles seed 0 — those bullets cannot both hold. Worse, most M2 cards crash the M1.5 engine when drawn (new NOUNs raise in `_evaluate_has`; OP-only comparators raise in `_parse_quant`; operator MODIFIERs land in QUANT and raise the same way). Even silently-safe additions (ANYONE/EACH no-op via empty scope; JOKERs stay in-hand) regressed the M1.5 watchable smoke 0/10 vs 6/10 baseline. The worker chose the hard constraint, held the deck composition byte-identical, documented the rationale inline in cards.yaml, and flagged the deviation in the handback. Orchestrator merged with accept-and-file-followup.

## Root cause

The ticket was shaped before its consumer-side dependencies were cataloged. The DoD assumed "add data + extend deck = M1.5 keeps working" because previous content tickets (RUL-17 baseline) followed exactly that shape. But the new M2 cards are not drop-in compatible with M1.5 consumers — every new SUBJECT/NOUN/MODIFIER/JOKER variant requires a Phase 3 engine ticket to teach a consumer how to handle it. The deck-extension belongs in each Phase 3 consumer-wiring ticket, not in the substrate-and-data ticket. The orchestrator wrote the ticket from the inventory docs (which list the cards) without walking the consumer side (`_evaluate_has`, `_parse_quant`, `_scope_subject`) to ask "what would happen if a fresh card showed up at every consume site". The worker's flag is the right resolution; what's missing is a ticket-shape rule that prevents the contradiction in the first place.

## Fix in project

- The Phase 3 fan owns deck-extension per consumer wiring. Captured in STATUS.md "Phase 3 cross-cutting requirement" so each Phase 3 ticket's DoD includes "extend `deck:` for the cards your consumer now handles".
- For the next substrate-and-data ticket: the DoD should explicitly list "data is loadable; deck composition unchanged" rather than "add data and extend deck", with the deck extension belonging to the consumer-wiring ticket.

## Proposed template change

Ticket-shape rule for "introduces vocabulary that downstream code will consume" tickets (a pattern already covered in part by the 2026-05-09 cross-reference lesson): when the deliverable is data + a substrate field, the DoD must split into (a) **data loadable** (parser + tests) and (b) **data observable in the runtime path** (consumer wiring + smoke regression). If (b) lives in a separate ticket, (a)'s DoD must explicitly include "the new vocabulary is data-only at this stage; deck composition / runtime exposure is held identical to the prior milestone". Otherwise the contradiction surfaces at the worker rather than the ticket-author. Worth promoting to global `CLAUDE.md` ticket-shape rule because it generalises beyond cards: every protocol-shape ticket, every status-token ticket, every label-key ticket has the same risk.

---

---
date: 2026-05-10
ticket-context: RUL-39, RUL-44, RUL-46, RUL-42, RUL-43, RUL-23
template-worthy: yes
---

## What happened

D's PR (RUL-39) replaced the M1.5 `+1 VP` stub in `effects.resolve_if_rule` with a `revealed_effect`-driven dispatcher. D's own tests pinned `revealed_effect = GAIN_VP:1` on shared state helpers in `test_resolver.py` and `test_persistence.py` so the existing `+1 VP` assertions still landed. But every other Phase 3 worker (RUL-44 I, RUL-46 K, RUL-42 G, RUL-43 H) authored their own test fixtures BEFORE D was on `origin/main` — their fixtures constructed `GameState(...)` without a `revealed_effect` pin and asserted `vp == 1` post-resolve.

GitHub merge mechanics reported each PR as `MERGEABLE / CLEAN` against post-D `main` because the diffs touched different functions / files (no auto-merge collisions). The orchestrator merged I (RUL-44) on green mergeability — and broke main: 15 tests in `test_effects_nouns.py` started failing. Same pattern recurred for K's `test_goals.py` (2 failures). Then G's rebase exposed a separate cascade: G adds 10 cards to `cards.yaml deck:`, which reshuffles seed-0 deals in `test_round_flow.py` — 14 pre-existing tests that relied on the lucky M1.5 seed-0 deal containing a SUBJECT card started failing.

All three issues were post-merge regressions on `main`. Each required an orchestrator-authored RUL-23 fix-forward commit:
- `RUL-23: pin revealed_effect on test_effects_nouns helpers` (15 failures → 0)
- `RUL-23: pin revealed_effect on test_goals enter_resolve helpers` (2 failures → 0)
- `RUL-23: make _drive_to_first_build seed-independent` (14 failures → 0)
- `RUL-23: inject SUBJECT for direct start_game test` (1 failure → 0)

Then G and H each needed in-PR test-helper amendments to add the `revealed_effect` pin to their own test fixtures. Total: 4 RUL-23 commits + 2 worker amendments to recover from a cascade kicked off when I merged on CLEAN-but-broken state.

## Root cause

Two reinforcing factors. (1) **Orchestrator's spot-check rule (`workflows/pr-merge.md` step 1.5) verifies the PR's own DoD against its own diff. It doesn't verify the PR's tests still pass against post-merge `main`.** GitHub's `mergeable: CLEAN` only attests to merge-mechanics; it has no test-running CI in this repo. The orchestrator never ran the PR's tests in a rebased-against-main state before merging. (2) **D's substrate change was substantive** — `revealed_effect` becomes a required field for any test that asserts post-resolve VP changes — but the substrate-watchpoint guidance in `PROJECT_CONTEXT.md` covers state.py changes only. Behavioural substrate (a function's contract) has no equivalent watchpoint, so workers and orchestrator both missed that D's contract change rippled into every other Phase 3 PR.

Separately, the `_drive_to_first_build` fragility was pre-existing (the helper relied on lucky seed-0 deals containing a SUBJECT) but didn't manifest until Phase 3's deck extensions arrived. RUL-31 dodged it because it held the deck identical (and was the lesson that taught us "Phase 3 owns deck extension"); RUL-34 hardened the M1.5 watchable smoke against the same fragility but didn't generalise the fix to `_drive_to_first_build`.

## Fix in project

- Memory rule (existing): "spot-check one DoD bullet against the diff before merging" tightened in practice to also include "rebase against post-merge main and run the affected test files before merging" when a previously-merged PR in the same fan touched a contract every other PR consumes.
- Cross-cutting helper fix in `_drive_to_first_build` (84ecde9) makes the test-suite seed-independent. Future deck-extending tickets won't trip this.
- The four RUL-23 commits document the recovery; cumulative cost was ~30 minutes of orchestrator time but should never have happened.

## Proposed template change

`workflows/pr-merge.md` step 1.5 should grow a sub-bullet: "If the PR is part of a parallel fan where a sibling has already landed a contract change (signature, behavioural substrate, required-field addition), rebase the PR's branch against post-merge main and run the affected test files before squash-merging. CLEAN merge mechanics are not sufficient evidence that the rebased state is green."

Substrate-watchpoint section in `PROJECT_CONTEXT.md` could grow a behavioural-substrate clause: "When a PR changes the contract of a public function (signature, required-field consumption, exception class), every test that constructs a `GameState` (or equivalent fixture) for the affected code path is implicitly impacted. List the contract change in the PR description and propose a helper-pin pattern for downstream test fixtures." The orchestrator dispatching parallel siblings should bake the helper-pin into all dependent tickets' hand-overs.

Worth promoting to global `CLAUDE.md`: "Behavioural substrate" alongside "code substrate" — both deserve watchpoints. CLEAN merge mechanics is necessary but not sufficient when a parallel fan shares behavioural substrate.

---

---
date: 2026-05-10
ticket-context: RUL-47, RUL-54, RUL-35
template-worthy: yes
---

## What happened

RUL-47 added an `rng=None` parameter to `enter_round_start` for the new effect-deck-recycle path. The fallback was `rng if rng is not None else random.Random()` — a fresh, unseeded `random.Random()` whenever the caller didn't pass one. RUL-47's PR review (mine) caught all the test fixtures that fire on round 1 (the existing fixtures all built minimal multi-round games); none of them exercised the recycle, because the recycle path only triggers once the 12-card effect deck exhausts — at round ~13. CI green. Squash-merged.

The CLI (`cli.py:85`) was never updated to thread an rng through its `advance_phase(state)` call for `ROUND_START`. So in production: `cli.run_game(seed=0)` ran deterministically for ~13 rounds, then `_draw_effect_card` hit `if not deck: ... rng.shuffle(deck)` with `rng=random.Random()` (the unseeded fallback), and the rest of the game went non-deterministic. Same `--seed 0` produced different winner outcomes per invocation. Two latent twin foot-guns (same `rng or random.Random()` shape) lived at `enter_resolve` step 12 and `_refill_hands` — currently masked because the CLI passes `refill_rng` to both, but waiting for the next caller to forget.

RUL-35 (the M2 watchable smoke) was the first thing that exercised the >13-round path with 10 seeds × 5 back-to-back sweeps. Its worker probed, observed 4–6/10 winner variance across identical invocations, traced it back to the unseeded fallback, and correctly stop-condition'd rather than build the smoke on top of a non-deterministic substrate. RUL-54 filed and dispatched as a substrate-fix blocker; landed via PR #50 (shape (b) — `rng=None` tolerated only when the reshuffle does not fire; raises `ValueError` at the reshuffle site otherwise; new `effect_rng = random.Random(seed ^ 0xEFFC)` disjoint stream in the CLI). 429/429 tests, 4 new (incl. `test_determinism.py` byte-identical-stdout invariant past the recycle threshold).

## Root cause

Behavioural-substrate cascade at *depth*, not at width. The 2026-05-10 prior lesson (revealed_effect pin cascade) covered width — a contract change ripples across parallel siblings within a single fan. This is the same shape but on the time-of-trigger axis: a fallback that's silent until N rounds into a game (or N retries into a job, or N MB into a file, etc.) escapes any PR review that doesn't deliberately exercise the deep path. The PR-merge spot-check rule reads the diff and asks "does the DoD bullet appear here". It does not ask "what's the depth/time horizon at which this contract change first bites?" That's a different question and it was the right question to ask of RUL-47.

A second factor: `rng or random.Random()` is a tempting Python idiom for "make this work without a seed when nobody passes one". It's specifically dangerous when the function will be called from a context that *expects* determinism (cli.py threading a seed through) but the rng parameter is only consumed conditionally (here, conditional on the recycle path triggering). The idiom mixes "deterministic when caller cares" with "non-deterministic when caller doesn't" — and the only way to know which mode you're in is to know whether the conditional path fires, which depends on runtime state.

## Fix in project

- RUL-54 PR #50: shape (b) lands. `rng=None` tolerated when the reshuffle does not fire; `ValueError("seeded rng required to recycle effect_discard into effect_deck")` at the site when it does. CLI gains `effect_rng = random.Random(seed ^ 0xEFFC)` and threads it through `advance_phase` for ROUND_START. Twin sites at `enter_resolve` step 12 and `_refill_hands` get the same `raise ValueError` shape so they can't silently regress later. `test_determinism.py` exercises round ≥ 13 on 3 seeds and asserts byte-identical stdout across back-to-back invocations.
- RUL-35 re-dispatched against post-RUL-54 main; worker's pre-fix probe noted 4–6/10 winner variance, so the deterministic baseline likely sits at the 5/10 boundary. Phase 3.5 polish pre-allocated; only filed if RUL-35 lands at <5/10.

## Proposed template change

`workflows/pr-merge.md` step 1.5 should grow a second sub-bullet: "If the PR adds a new code path that fires conditionally on runtime state (deck exhaustion, retry counter, accumulated history, etc.), state explicitly in the PR description: 'this path first fires at <depth/time>'. Spot-check by reading the diff for the conditional and asking whether any existing test reaches it. If no test does and the path is reachable in production, file the missing test as a sibling of the original ticket — the path exists in some sense the moment it's mergeable, not the moment the first user hits it."

`workflows/feature-work.md` (or a worker-contract doc): when adding a parameter with a `param or <default>` fallback shape to a public function, the hand-back must answer two questions explicitly: (1) "what happens when the fallback is consumed?" and (2) "is the fallback ever consumed in production?" If (1) is non-deterministic and (2) is yes, the fallback is a trap — raise instead, or make the parameter required, or pin a deterministic default.

Worth promoting to global `CLAUDE.md`: "Conditional substrate" — a code path that fires only on rare runtime state — is the third axis of substrate watching, alongside "code substrate" (file-level shape) and "behavioural substrate" (function-level contract). Code-substrate is caught by additive-only review; behavioural-substrate by rebase-and-test-against-post-merge; conditional-substrate by *depth-aware* review (does any test reach this branch?). The three lesson families compose: a PR can change a public-function contract (behavioural) on a conditional path (conditional) that no existing test reaches (depth) — that's exactly the shape RUL-47 had.

---

---
date: 2026-05-10
ticket-context: RUL-55, RUL-31, RUL-34
template-worthy: maybe
---

## What happened

RUL-55 worker probed Lever B (deck rebalance — bumping SUBJECT counts in `design/cards.yaml deck:` by 1–2 each) as the second route to push the M2 watchable smoke from 5/10 → 7/10 winners. The hand-over warned about `_drive_to_first_build` fragility (a known issue post-Phase-3 — see the 2026-05-10 "deck-size fragility in test helpers" entry) and reminded the worker to rebase before assuming it's now seed-independent.

What the worker actually found: every Lever-B config that hit ≥7/10 broke a different set of tests via a *different* fragility — the **goal-pool shuffle cascade**. Bumping the deck composition changes the order in which `start_game(seed=0)` consumes the seeded rng, which shifts the goal-pool shuffle (RUL-46 K's `tuple(goal_pool)` post `rng.shuffle`), which lands different goal cards in `active_goals`, which cascades into:

- `test_cards_loader` (asserts on specific cards present in the loaded deck — directly broken by counts change)
- `test_determinism.test_recycle_path` (the recycle path is reached at round ~13 via specific in-play card draws — shifted by the upstream deck change)
- `test_jokers.test_full_game_round_trip_with_persistent_when_joker` (asserts joker attaches on a specific round — shifted by the chain of upstream draws)

Worker correctly chose Lever A (PLAY_BIAS tuning, single-line behavioural change with no deck consumption shift) and rejected Lever B. PR #56 landed at 7/10 via Lever A alone; the orchestrator merged it.

## Root cause

The 2026-05-10 "deck-size fragility in test helpers" lesson focused on `_drive_to_first_build` and shipped a fix making *that* helper seed-independent. But the deck-composition fragility was wider: any test that constructs `start_game(seed=N)` and asserts on specific downstream state (loaded card identities, joker attachment rounds, the recycle path landing on a specific round) is implicitly fragile to deck-counts changes — not because the test depends on lucky seed-0 deals, but because the rng consumption order chains across `cards.shuffle(deck)` → `cards.shuffle(goal_pool)` → all subsequent `start_game` draws → all subsequent `_refill_hands` draws → the round at which any specific in-play assertion lands.

The existing watchpoint in `PROJECT_CONTEXT.md` ("Substrate-and-data tickets must split DoD into (a) data loadable + (b) data observable in runtime") doesn't cover *which downstream tests will silently break* when (a) ships even with (b) deferred. The fragility surfaced because RUL-55's worker tried the deck-rebalance lever and observed the failure pattern — but the lesson would have been invisible if RUL-55 had stuck with Lever A from the start.

## Fix in project

- STATUS.md "Open judgment calls" now lists the three test files that must be rebased + run when a PR changes `cards.yaml deck:` composition. Future deck-rebalance tickets reference this list explicitly.
- Memory rule on the hand-over path typo saved (`feedback_cards_yaml_path.md`): `design/cards.yaml`, not `engine/data/cards.yaml`. Wrong-path hand-overs cost reading time + lookup overhead and may mislead workers about what they're touching.

## Proposed template change

`workflows/pr-merge.md` step 1.5 sub-bullet (existing): "If the PR is part of a parallel fan where a sibling has already landed a contract change, rebase the PR's branch against post-merge main and run the affected test files before squash-merging." Extend with: "If the PR changes `design/cards.yaml deck:` composition (counts of any card kind), the *affected test files* explicitly include `test_cards_loader.py`, `test_determinism.py`, and `test_jokers.py::test_full_game_round_trip_with_persistent_when_joker` — these are the known fragile downstream sites as of 2026-05-10. Re-probe + extend this list when the next deck-rebalance candidate fails on a new test."

Per-project candidate for a `tests/seed_dependency_index.md` doc: maintain a small index of "tests fragile to deck composition" so workers and orchestrator have a single page to consult before deck changes. Promote to global protocol if the same pattern surfaces in another project (rng-consumption-order fragility is generic across any deterministic engine).

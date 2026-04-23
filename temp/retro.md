# Epic #123 retrospective — findings

Post-execution review of the server-driven `/me/bootstrap` epic (29 GitHub issues, Phase 0 through Phase 4). Observations anchored in session moments and in the on-disk Maverick codebase at `~/projects/maverick`.

## 1. Software development issues

### 1.1 Avoidable failures

**Orphan-merge of PR #173.** Stacked `feat/142-admin-guard-bootstrap` on top of `feat/140-wire-bootstrap-provider` before `feat/140` was merged. The user merged `feat/140` → develop, then 25 seconds later merged `feat/142` → `feat/140` — but `feat/140` was already an orphaned reference at that point. GitHub marked PR #173 "merged" but the code never reached develop. Detected only when AdminGuard's old code was still on develop. Recreating as PR #174 cost ~10 minutes and required re-cherry-picking the commit.

- _Root cause:_ chaining PRs to sidestep "waiting for the user to merge." The trade-off was a brittle dependency on merge ordering.
- _Mitigation:_ either (a) never stack, (b) auto-retarget the stacked PR when its base is merged, or (c) a Maverick skill that detects "my base is fully contained in develop" and automatically retargets before merge.

**Test mock discovery cycles.** For almost every new test file: two iterations on mocks. First attempt used a plausible shape, then hit runtime failures from `app/src/test/setup.ts`'s global mocks hiding real exports. Affected: `store/api` (missing `api`), `@comp/loaders` (only exports `AppLoader`), `react-router` (only exports `useNavigate`/`useLocation`), `@nitpick/shared` (missing `organisationTypeCodes` etc.), and the knex `.catch()` thenable pattern. Each added ~1 minute of edit-run-fix.

- _Root cause:_ the global mock factory `createMockNitpickShared()` is a hand-curated subset. Nothing signals which real exports are missing until runtime.
- _Mitigation:_ either (a) auto-include-all pattern (partial mock with `...importOriginal()`), which the test-tools package could expose as `createRealOrMockNitpickShared()`, or (b) document the "override global mocks locally" pattern once in a project skill so Claude picks it up without trial-and-error.

**BootstrapProvider unauth gap — caught late.** First cut of `#137` assumed signed-in users only. Wiring into app.tsx in #140 would have broken signin/signup routes. Caught it while writing #140 and did a second pass on #137's code inside the #140 PR. Not broken, but backtracking.

- _Mitigation:_ spec #137 should have called out the "render on both auth states" requirement explicitly. Or #137's code-review should have asked "what happens when this wraps signin/signup?"

**Hook false-positives on push.** `block-dangerous-git.sh` incorrectly flagged normal first-pushes of `feat/138` and `feat/146` as "force push," requiring manual user intervention. The block happened mid-workflow, ~3–5 minutes lost each time on diagnosing.

- _Root cause:_ the hook's heuristic is overzealous. Claude could not read the script to diagnose (permission blocker) which is itself a friction source.

**`routes.meBootstrap` slash-convention mismatch (#127).** Issue body said `'/me/bootstrap'`; codebase convention was no leading slash. Followed convention and called it out in the PR, but this is the kind of rough edge that compounds across many issues.

### 1.2 Time consumers

**Pre-commit `make g-lint-all` on every commit.** Single biggest time sink. `.pre-commit-config.yaml:52-81` runs `g-lint-all` against the whole monorepo even when only one package changed. On feature branches (where Environment Preparation / Code Build / Unit Testing are all skipped), the lint step still runs — 2–5 minutes per commit. Across ~25 commits for this epic, that's ~1.5 hours of pure lint wait.

**Docker-based gitleaks.** Also runs on every commit. ~5–10s overhead but compounds at 25+ commits.

**Subagent dispatches for small issues.** For `#127` (one-line addition), `#134` (two-line addition), `#135` (single test file) the issue-analyst subagent was dispatched anyway because `do-issue-solo` requires it. Each dispatch is 2–5 minutes. For trivial issues this was overkill.

**E2E can't be locally verified.** The E2E tests written for #135, #149, #150 needed Clerk credentials + live API + Playwright browsers. Could confirm they compile and lint but not actually run them. Value-of-review is limited until CI runs them post-merge.

**Full CI per PR.** 5–10 minutes to run `PR Validate` workflow on each of ~20 PRs. Total CI: 1.5–3 hours across the epic.

## 2. Maverick LLM toolset use

### 2.1 Why Claude needed assistance

**Code review was not consistently dispatched, and was never enforced.** `~/projects/maverick/skills/do-issue-solo/SKILL.md` Phase 6 mandates dispatching `agent-code-reviewer`, but the reviewer's verdict is only advisory — it returns text to Claude. There is no `gh pr review --approve` step, no hand-off to a bot reviewer, no mechanism to mark the PR as "Claude-reviewed." The human must still review and approve.

Honest audit of Claude's own adherence: dispatched `agent-code-reviewer` for #125, #126, #128. After that Claude got into a rhythm of pushing PRs without the review dispatch for Phase 2 and most of Phase 3 — there is no hard gate in the skill that forced it. **Most of the PRs the user merged were not code-reviewed by an agent** — just lint+test verified. This is a Maverick skill-adherence failure on Claude's part, and a skill-design gap on Maverick's side (no enforcement, no checklist item in the completion comment that says "reviewed by agent-code-reviewer on YYYY-MM-DD").

**Serial by construction.** Maverick's `do-issue-solo` is designed for one issue at a time. No skill orchestrates a dependency graph of issues. The `mav-claude-code-recovery` skill mentions "if working on multiple issues concurrently (e.g., in worktrees)" but provides no concurrency primitives. User's global policy (no worktrees) combined with this gap forces one-issue-at-a-time.

**No epic-level skill.** Nothing in `~/projects/maverick/skills/` reads an epic issue's task-table, builds a DAG, and sequences waves. Claude had to maintain that mental model manually, supported by its own TaskCreate list.

**No stacked-PR guidance.** `~/projects/maverick/skills/mav-git-workflow/SKILL.md` assumes all branches target `main` (or here, develop). No mention of stacking, no mention of "retarget when your base merges." That gap produced the orphan-merge incident.

**No state across issues.** `.claude/issue-state.json` is scoped to one issue. Between issues, Claude rebuilt context from GitHub issue text each time, re-reading the epic's task table. An epic-state file would eliminate this.

### 2.2 What could have been parallelised

With the existing dependency graph (from epic #123's task-table), the issue execution could have compressed dramatically. Waves of issues that share no file conflicts and share no sequential deps:

| Wave | Issues                 | Notes                                                                                                                |
| ---- | ---------------------- | -------------------------------------------------------------------------------------------------------------------- |
| 0a   | #124, #125, #126, #127 | All Phase 0 — different files in shared/. #124 was already merged, so realistically **#125 + #126 + #127 parallel**. |
| 0b   | #138                   | Phase 2 component (FatalError). Parallel with wave 0a.                                                               |
| 1a   | #128                   | Phase 1 entry. Depends on Phase 0 merged.                                                                            |
| 1b   | #136, #139             | Both depend on Phase 0 merged. **Parallel with 1a.**                                                                 |
| 2a   | #129, #130, #134       | All three only depend on #128. **3-wide parallel.**                                                                  |
| 2b   | #137                   | Depends on #136 + #138. Parallel with 2a.                                                                            |
| 3    | #131, #132             | Both depend on #129 + #130. **2-wide parallel.**                                                                     |
| 4    | #133, #140, #141       | #133 blocks on Phase 1; #140 blocks on #137; #141 blocks on #139. **3-wide parallel.**                               |
| 5    | #135                   | Needs #133 + #134.                                                                                                   |
| 6    | #142, #143, #144, #148 | All four only need #140 merged. **4-wide parallel.**                                                                 |
| 7    | #145, #147             | Both need #144. **2-wide parallel.**                                                                                 |
| 8    | #146                   | Needs wave 7 merged.                                                                                                 |
| 9    | #149, #150, #151, #152 | All four unblocked in parallel after Phase 3 complete. **4-wide parallel.**                                          |

**10 waves instead of ~26 serial issues.** Roughly 2.5× speedup on issue count alone, before counting merge-wait and lint-wait savings from fewer total sequential pauses.

The parallelism bottleneck is the local checkout, not the agent model. Concretely:

- Two sibling PRs that touch the same file (e.g. `shared/src/index.ts` barrel export) will collide. Wave 0a's #125/#126/#127 each append to `index.ts` — if done in parallel by subagents on one checkout, the second subagent's commit would have to rebase. Solvable via worktrees or by designating one subagent as "barrel-export consolidator."
- Two sibling PRs that touch the same package's tests can race on the pre-commit hook (which runs lint for the whole monorepo). Solvable by scoping hooks per-package.
- Subagent pre-commit docker usage — `gitleaks` via docker has some filesystem lock concerns if run concurrently. Needs testing.

**Pragmatic next step** if the user does not want to re-enable worktrees: a Maverick skill that executes waves as "batch several issues serially in a single Claude run, then human merges the batch, then next wave" — which is effectively what happened ad-hoc, but promoted to a first-class skill with DAG awareness. That alone would cut the merge-coordination overhead significantly.

## 3. Improvements to prioritise

Ordered by **impact × implementability** (high first).

### Priority 1 — scoped pre-commit lint (massive win, small code change)

`.pre-commit-config.yaml` runs `make g-lint-all` on every commit. For a monorepo this is the biggest wall-clock time sink. Either:

- Replace with `turbo run lint --filter=...[HEAD~1]` or `pnpm --filter ...[HEAD^]` to scope to changed packages
- Or a small bash wrapper that greps staged files for their package and runs `make <pkg>-lint` only for those

This one change would have saved ~1.5 hours of cumulative wait on this epic alone.

### Priority 2 — Maverick `do-epic` skill

New skill at `~/projects/maverick/skills/do-epic/SKILL.md`. Responsibilities:

1. Takes an epic GitHub issue number
2. Parses the task-table comment (already a Maverick convention per `mav-github-issue-workflow`) into a DAG
3. Runs issues in dependency-correct order
4. For each "wave," decides: single `do-issue-solo` run (if wave is one issue) or serial-within-wave (if worktrees disallowed) or dispatch-parallel-subagents (if policy permits)
5. Maintains an epic-state file: which issues are merged, in-PR, or blocked
6. After each wave, summarises PRs opened and asks the user to merge before continuing
7. Detects when a PR's base becomes obsolete (merge-base against develop is a superset) and retargets

This is the single biggest workflow improvement for epics. Even without parallel subagents, the wave-aware scheduling + merge-coordination + orphan-merge detection would have avoided most of the friction hit during epic #123.

### Priority 3 — enforce agent-code-reviewer dispatch

`do-issue-solo/SKILL.md` Phase 6 should be non-skippable. Two hardening options:

- **Soft:** the completion-comment template in `mav-github-issue-workflow/SKILL.md` adds a mandatory "Code review: <agent verdict> at <timestamp>" line. If Claude posts completion without it, the skill flags it.
- **Hard:** the skill refuses to run the PR-creation step until it sees the reviewer's verdict text in the session. Requires some mechanism for the skill to inspect prior tool calls.

Also: add an **optional self-approve** step using `gh pr review --approve` signed by a bot account (`maverick-bot`) that runs only after `agent-code-reviewer` returns a PASS verdict. Even without a true second set of eyes, this would create an auditable "reviewed by agent" trail and unblock auto-merge policies if used.

### Priority 4 — stacked-PR pattern skill

New skill at `~/projects/maverick/skills/mav-stacked-prs/SKILL.md` (or amend `mav-git-workflow`). Covers:

- When stacking is appropriate (dependent issues that can't wait to merge serially)
- How to target base = `feat/parent-branch` explicitly in PR creation
- The retarget-after-merge pattern: when `git merge-base HEAD develop` shows the base is fully in develop, retarget to develop and push (this would have saved the #173 orphan merge)
- When NOT to stack (default to develop when dependency is already merged)

Make `do-issue-solo` aware of this skill when it sees an uncommitted dependency.

### Priority 5 — partial-mock convention as a project skill

Add a tiny `app/docs/testing-mocks.md` (and api equivalent) that documents the partial-mock override pattern for overriding `app/src/test/setup.ts`'s global mocks. Saves Claude from the two-iteration discovery each time. Cross-reference from any `mav-bp-unit-testing`-style project skill.

### Priority 6 — epic-scope state file

`.claude/epic-state.json` alongside per-issue state. Tracks: epic number, merged issues (by URL), in-flight PRs, blocked-on-merge issues, current wave. Lets a Claude run pick up where a previous Claude run left off without re-reading the full epic task table.

### Priority 7 — Maverick-bot reviewer + auto-merge

Separate bot account `maverick-bot`; plumb `GH_TOKEN` so `gh pr review --approve --body "..."` posts under that account after `agent-code-reviewer` returns PASS. Combined with GitHub's auto-merge on green CI, the merge-wait pause between waves could collapse from human-minutes to CI-minutes.

### Priority 8 — worktree-based parallel subagents (optional, gated by user preference)

The user's global `~/.claude/CLAUDE.md` forbids worktrees. For a 4-wide parallel wave (like Phase 3 issues #142/#143/#144/#148), worktrees are the clean answer. If open to allowing them **for do-epic runs specifically**, Maverick could: create N worktrees, dispatch N subagents one per worktree, collect results, merge their branches back to main checkout. Each subagent works in isolation; no file-level collisions. Ship this behind an opt-in flag so the baseline policy stays intact.

## Net impact estimate

If the top 3 items landed before the next 29-issue epic: roughly **50–60% wall-clock reduction** (priority 1 saves lint time, priority 2 saves merge-wait + coordination time, priority 3 catches review gaps that currently silently pass).

---
name: do-issue-solo
description: Work on a GitHub issue end-to-end autonomously, only pausing when blocked or when clarification is needed.
argument-hint: issue number (e.g., 123)
user-invocable: true
disable-model-invocation: false
---

**Depends on:** mav-scope-boundaries, mav-multi-instance-coordination, mav-durability-on-gh, mav-block-propagation, mav-git-workflow, mav-stacked-prs, mav-github-issue-workflow, mav-create-solution-design, mav-create-tasks, mav-plan-execution, mav-local-verification, mav-bp-cicd, mav-bp-remote-code-review, mav-claude-code-recovery, mav-bp-logging, mav-bp-alerting, mav-systematic-debugging, do-docs, do-pullrequest-review

# Work on GitHub Issue (Autonomous)

Work on GitHub issue `` autonomously, coordinating safely
with any other Maverick instance that might also hold a claim on this
issue. Follow every phase in order. Only pause to ask the user when you
are blocked or need clarification.

## Preflight (mandatory)

Run this **first**, before reading any other phase. If it exits non-zero,
halt and report the stderr output verbatim to the user. Do not proceed,
do not work around missing prerequisites.

```bash
uv run maverick preflight do-issue-solo
```

The check verifies: the project is initialised, the mandatory remote
code-review workflow is in place, the maverick-bot is configured,
and required tools (`gh`, `git`, `uv`) are on PATH.

## Before You Begin

If `` is empty or not a valid issue number, ask the user
for the issue number before proceeding.

Determine the repo (via `gh repo view --json nameWithOwner`) — you will
pass it to every `maverick coord` command below.

If preflight reported a missing `code_review_workflow` flag, offer the
user two paths before claiming the issue:

1. **Scaffold the reference workflow.** Copy
   `${CLAUDE_PLUGIN_ROOT}/skills/mav-bp-remote-code-review/code-review.yml`
   into `.github/workflows/`, commit it on a small setup branch, open a
   PR for it, and wait for the user to merge that PR before continuing
   with ``. After the workflow merges, run
   `uv run maverick integration set code_review_workflow true` and
   re-run `uv run maverick preflight do-issue-solo`.
2. **Abort.** If the user declines, stop here.

## Phase 0: Coordination + cold-start

This phase is new in the workflow overhaul. Before any other phase.

1. Run `uv run maverick coord read <repo> ` and inspect
   the snapshot. Decide which of the four branches in
   `mav-multi-instance-coordination` applies:
   - **Blocked** (`blocked-by:#N` label): abort cleanly, report to user.
   - **Claimed with live lease**: abort cleanly, report holder + expiry.
   - **Claimed with stale lease**: decide take-over vs defer.
   - **Free**: proceed to claim.
2. Claim the issue: `uv run maverick coord claim <repo> `.
   The command exits non-zero if the claim is rejected — treat that as
   abort.
3. Start a heartbeat loop that refreshes the lease every
   `HEARTBEAT_INTERVAL_MINUTES` minutes for as long as you hold the
   claim. If two consecutive heartbeats fail, treat the claim as lost
   and abort (do not push further work).
4. Register a release handler that fires on every exit path (success,
   eject, abort): `uv run maverick coord release <repo>  --reason <reason>`.
5. Cold-start hydrate per `mav-durability-on-gh`:
   - Read open PRs: `gh pr list --head <branch> --json number,state`
   - Read the tasks comment on the issue
   - Check for an existing worktree for this issue under `.maverick/worktrees/`
   - If any state exists, resume at the appropriate phase rather than re-doing work.

## Phase 1-2: Understand the Issue and Solution Design (subagent)

Run Phases 1 and 2 as a subagent to keep the main context window clean for
implementation.

1. Initialise the issue state file per the
   mav-github-issue-workflow skill.
2. Dispatch the **agent-issue-analyst** agent with:
   - Issue number: ``
   - Mode: `solo`
3. When the agent returns, verify:
   - `.claude/issue-state.json` has `phase` set to `design`
   - `.claude/issue-state.json` has `comments.design` set to a comment ID
4. If the agent flagged ambiguities it could not resolve, ask the user.
   Otherwise continue.

## Phase 3: Create Tasks (subagent)

Run Phase 3 as a subagent.

1. Dispatch the **agent-github-issue-planner** agent with:
   - Issue number: ``
   - Design comment ID from `.claude/issue-state.json`
2. When the agent returns, verify:
   - `.claude/issue-state.json` has `phase` set to `tasks`
   - If < 5 tasks: `.claude/issue-state.json` has `comments.tasks` set to a comment ID
   - If >= 5 tasks: `.claude/issue-state.json` has `has_sub_issues` set to `true`
3. If the agent flagged scope concerns, ask the user.

## Phase 4: Create Worktree + Branch

This phase has changed in the overhaul. The branch is created **inside a
dedicated worktree**, not in the main checkout.

1. Derive the branch name per the mav-github-issue-workflow skill.
2. Resolve the base branch via `mav-git-workflow`'s default-branch
   lookup (`gh repo view --json defaultBranchRef -q .defaultBranchRef.name`).
   - If this story depends on a sibling story whose PR is open but not
     merged, stack per `mav-stacked-prs` — base = sibling branch.
3. Create the worktree: `uv run maverick worktree create <branch> [--base <sibling-branch>]`.
   From this point on, all file edits happen inside the worktree path.
4. `cd` into the worktree path for the rest of the story.
5. Update phase to `branch` in the state file.

## Phase 5: Execute Tasks (push after every task)

This phase has changed. **Push after every task, not at the end.** See
`mav-durability-on-gh`.

1. Read project-level skills at `docs/maverick/skills/`. Apply any
   topic-specific guidance they carry.
2. Update phase to `implement` in the state file.

**For each task (sub-issue or checklist item), in order:**

1. Implement the change.
2. Run local verification per `mav-local-verification` (lint,
   typecheck, tests).
3. If verification fails, diagnose per `mav-systematic-debugging`
   and fix. Do not commit red.
4. Create a conventional commit referencing the issue number.
5. **Push immediately**:
   - If this is the first push on the branch, set upstream:
     `git push -u origin <branch>`.
   - If on a stacked branch, run the retarget check per
     `mav-stacked-prs` **before every push**.
6. Update the tasks comment (or close the sub-issue).
7. Heartbeat: `uv run maverick coord heartbeat <repo> ` if it
   is time for a refresh.

After the last task, run the full verification suite once more.

Follow `mav-plan-execution` for the broader execution loop,
verification discipline, failure handling, and crash recovery.

## Phase 6: Documentation Review (mandatory)

This phase **always runs** before the PR is opened. There is no skip
path — the heuristic-gated version of this phase used to let stale docs
ship when Claude's affected-or-not call was wrong. The agent decides
whether work is needed; the workflow decides whether the agent runs.

1. Compute the full diff: `git diff origin/<base>...HEAD`.
2. Dispatch **agent-tech-docs-writer** with:
   - **Mode:** `update` (per `do-docs`)
   - **Diff:** the output of step 1
   - **Instructions:** review every changed file. Decide for each whether
     existing `docs/` content is now stale, or whether a new document is
     needed for a new component, subsystem, or architectural change with
     no existing coverage. Update or create accordingly. Returning
     "no doc changes required" is a valid outcome and must be reported
     explicitly (not silently inferred).
3. **Record the outcome** in the PR body or as a one-line PR comment so
   the gate is auditable:
   - If docs were updated or created: list the files changed.
   - If no changes were required: post `Docs review: no changes required.`
4. Commit any doc changes with a `docs:` conventional commit and push
   per the push-per-task rule.
5. The PR cannot proceed to Phase 7 until this phase has produced
   either committed doc changes or the auditable no-op record.

## Phase 7: Open PR + Monitor CI

1. Pre-push verification per `mav-local-verification` — a final
   green check before asking for review.
2. Stacked-PR retarget check per `mav-stacked-prs` if the branch
   stacks on a sibling. Retarget before opening the PR if the sibling is now
   merged.
3. Open the PR:
   ```bash
   gh pr create --base <resolved-base> --head <branch> \
       --title "<conventional title referencing #>" \
       --body "<summary + closes #>"
   ```
4. Monitor CI per `mav-bp-cicd`. If CI fails, read logs, fix
   locally, push. Do not proceed to Phase 8 until CI is green.

## Phase 8: Code Review (binary, hard gate)

This phase has changed. Review is now a **binary verdict** against the
open PR, not a local-diff advisory loop. See `agent-code-reviewer`.

1. Dispatch **agent-code-reviewer** with:
   - The PR URL
   - The issue body, design comment, and tasks list (so it has the spec)
2. The agent returns exactly one of two verdicts:
   - **PASS** — proceed to Phase 9 (merge).
   - **FAIL** — proceed to Phase 10 (eject). Do not attempt to auto-fix.
3. Update phase to `review` in the state file.

There is no fix-and-re-review loop. If the reviewer FAILs the PR, the
next step is eject-to-human, not iterate.

## Phase 9: Auto-merge (on PASS)

1. `maverick-bot` posts the approval:
   ```bash
   uv run maverick bot gh -- pr review <pr-url> --approve \
       --body "Approved by agent-code-reviewer at $(date -u +%FT%TZ)"
   ```
2. Enable auto-merge (squash):
   ```bash
   uv run maverick bot gh -- pr merge <pr-url> --auto --squash
   ```
   If CI was already green, GitHub merges immediately. Otherwise it
   merges when CI passes.
3. Post the completion comment on the issue per
   `mav-github-issue-workflow`.
4. Update phase to `complete` in the state file.
5. Release the claim: `uv run maverick coord release <repo>  --reason merged`.
6. Clean up:
   - Local state file
   - Destroy the worktree: `uv run maverick worktree destroy <worktree-path>`.

## Phase 10: Eject (on FAIL)

1. Post the reviewer's verdict as a PR comment:
   ```bash
   gh pr comment <pr-url> --body-file /tmp/review-verdict.md
   ```
2. Apply the `needs-human` label to both the PR and the issue:
   ```bash
   gh pr edit <pr-url> --add-label needs-human
   gh issue edit  --add-label needs-human
   ```
3. Request human review on the PR:
   ```bash
   gh pr edit <pr-url> --add-reviewer <human-handle>
   ```
4. If this story belongs to an epic (check `.claude/epic-state.json` or
   look for a parent epic reference on the issue):
   - Update epic state — mark this story `ejected`.
   - Trigger block propagation per `mav-block-propagation`:
     apply `blocked-by:#` to every transitive descendant.
   - Cancel any in-flight subagent work for stories now in the blocked set.
5. Release the claim: `uv run maverick coord release <repo>  --reason ejected`.
6. Do **not** destroy the worktree — the human may want to inspect it.
   Log the worktree path so the user can find it.

## Rules

- **Only pause for user input** when blocked or when the issue is ambiguous.
- **Never commit directly to the default branch.** All work flows through
  the feature branch → PR.
- **Always use conventional commits** referencing `#`.
- **Push after every task.** Durability trumps CI-cost optimisation.
- **Binary review.** PASS auto-merges; FAIL ejects. No fix loop.
- **Release the claim on every exit path.** Success, eject, abort, crash —
  all of them must release.
- **Never remove a `blocked-by:#N` label from inside the workflow.** Only a
  human may clear a block.

<!-- maverick-plugin-version: 0.5.8-dev -->

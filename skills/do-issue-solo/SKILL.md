---
name: do-issue-solo
description: Work on a GitHub issue end-to-end autonomously, only pausing when blocked or when clarification is needed.
argument-hint: issue number (e.g., 123)
user-invocable: true
disable-model-invocation: false
---

**Depends on:** mav-scope-boundaries, mav-multi-instance-coordination, mav-durability-on-gh, mav-block-propagation, mav-git-workflow, mav-stacked-prs, mav-github-issue-workflow, mav-create-solution-design, mav-create-tasks, mav-plan-execution, mav-local-verification, mav-bp-cicd, mav-bp-remote-code-review, mav-claude-code-recovery, mav-bp-logging, mav-bp-alerting, mav-systematic-debugging, do-code, do-test, do-docs, do-cybersecurity-review, do-pullrequest-review

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

The check verifies: the project is initialised, the Maverick GitHub
App is configured (`maverick gh-app status` reports `configured: true`),
and required tools (`gh`, `git`, `uv`) are on PATH.

## Before You Begin

If `` is empty or not a valid issue number, ask the user
for the issue number before proceeding.

Determine the repo (via `gh repo view --json nameWithOwner`) — you will
pass it to every `maverick coord` command below.

PR code review runs locally during Phase 9 as the
`agent-code-reviewer` subagent — its binary PASS/FAIL
verdict is the gate. Some projects also opt into a CI-side re-run via
`mav-bp-remote-code-review` (independent verification for
multi-machine fleets or audit needs); when present it adds a status
check the auto-merge in Phase 10 will wait on, but its absence is not
a blocker.

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
3. **Start the workflow report** (writes a `run-start` row that later
   `report` calls inherit `maverick_skill` from):
   ```bash
   uv run maverick report run-start do-issue-solo --issue  --phase claimed
   ```
4. Start a heartbeat loop that refreshes the lease every
   `HEARTBEAT_INTERVAL_MINUTES` minutes for as long as you hold the
   claim. The CLI provides a self-terminating foreground loop — run it
   in the background and let it exit on its own when `coord release`
   clears the claim label:
   ```bash
   uv run maverick coord heartbeat-loop <repo>  >/dev/null 2>&1 &
   ```
   If two consecutive heartbeats fail, the loop exits non-zero — treat
   that as claim-lost and abort (do not push further work).
5. Register a release handler that fires on every exit path (success,
   eject, abort): `uv run maverick coord release <repo>  --reason <reason>`.
6. Cold-start hydrate per `mav-durability-on-gh`. The
   skill is fully resumable — a fresh agent re-entering after a crash,
   stop, or context-exhaustion must skip phases that already completed
   rather than re-running them against an in-flight or merged PR (#41).

   Read **all** of:
   - `uv run maverick task-progress read <repo> ` — the
     phase boundary the previous agent last passed.
   - `gh pr list --head <branch> --json number,state,mergedAt` — open or
     merged PR for this issue's branch.
   - The tasks comment on the issue.
   - Existing worktree for this issue under `.maverick/worktrees/`.

   **Resume rules** (apply the first match, in this order):

   | Observed state | Resume at |
   |---|---|
   | PR exists, state=`MERGED` | Phase 10 step 4 (post completion comment, close issue, release claim, destroy worktree) |
   | PR exists, state=`OPEN`, CI failing | Phase 8 step 4 (fix CI, push) |
   | PR exists, state=`OPEN`, CI green, no review verdict | Phase 9 (dispatch reviewer) |
   | PR exists, state=`OPEN`, FAIL verdict on PR | Phase 11 (eject) |
   | task-progress phase ≥ `branch`, no PR | Phase 5 (continue tasks from last completion) |
   | task-progress phase = `tasks` | Phase 4 (create worktree + branch) |
   | task-progress phase = `design` | Phase 3 (create tasks) |
   | nothing | Phase 1 (start fresh) |

   Each phase below ends with a `task-progress set` write so re-entry can
   advance one boundary at a time without re-running anything.

## Phase 1-2: Understand the Issue and Solution Design (subagent)

Run Phases 1 and 2 as a subagent to keep the main context window clean for
implementation.

1. **Refresh the local base branch** before the analyst reads anything.
   The analyst runs against the main checkout — Phase 4 hasn't created
   the worktree yet — so a stale local base lets pre-resolved
   ambiguities slip into the design pass and surface as phantom
   blockers (#102). Follow the "Base Branch Freshness" rule in
   `mav-git-workflow`:
   ```bash
   STORY_BASE=$(uv run maverick git-workflow story-base)
   git fetch origin "$STORY_BASE"
   CURRENT=$(git rev-parse --abbrev-ref HEAD)
   if [ "$CURRENT" = "$STORY_BASE" ]; then
       git pull --ff-only origin "$STORY_BASE"
   else
       git fetch origin "$STORY_BASE:$STORY_BASE"
   fi
   ```
   If either form refuses a non-fast-forward, halt and report to the
   user — there are local commits on `$STORY_BASE` that have not been
   pushed, which violates trunk-based discipline.
2. Initialise the issue state file per the
   mav-github-issue-workflow skill.
3. Open the agent-dispatch interval: `uv run maverick report begin agent-dispatch --issue  --phase design --agent agent-issue-analyst --skill-name mav-create-solution-design`.
4. Dispatch the **agent-issue-analyst** agent with:
   - Issue number: ``
   - Mode: `solo`
5. Close the agent-dispatch interval: `uv run maverick report end agent-dispatch --issue  --phase design --agent agent-issue-analyst --skill-name mav-create-solution-design --outcome success`.
   (Use `--outcome failure` if the agent returned an error rather than a design.)
6. When the agent returns, verify:
   - `.claude/issue-state.json` has `phase` set to `design`
   - `.claude/issue-state.json` has `comments.design` set to a comment ID
7. If the agent flagged ambiguities it could not resolve:
   - Open the question interval: `uv run maverick report begin question --issue  --phase design --topic ambiguity-resolution`.
   - Ask the user.
   - Close it: `uv run maverick report end question --issue  --phase design --topic ambiguity-resolution --outcome success`.

   Otherwise continue.
8. **Checkpoint**: `uv run maverick task-progress set <repo>  design`.

## Phase 3: Create Tasks (subagent)

Run Phase 3 as a subagent.

1. Open the agent-dispatch interval: `uv run maverick report begin agent-dispatch --issue  --phase tasks --agent agent-github-issue-planner --skill-name mav-create-tasks`.
2. Dispatch the **agent-github-issue-planner** agent with:
   - Issue number: ``
   - Design comment ID from `.claude/issue-state.json`
3. Close it: `uv run maverick report end agent-dispatch --issue  --phase tasks --agent agent-github-issue-planner --skill-name mav-create-tasks --outcome success`.
4. When the agent returns, verify:
   - `.claude/issue-state.json` has `phase` set to `tasks`
   - If < 5 tasks: `.claude/issue-state.json` has `comments.tasks` set to a comment ID
   - If >= 5 tasks: `.claude/issue-state.json` has `has_sub_issues` set to `true`
5. If the agent flagged scope concerns:
   - Open the question interval: `uv run maverick report begin question --issue  --phase tasks --topic scope-concerns`.
   - Ask the user.
   - Close it: `uv run maverick report end question --issue  --phase tasks --topic scope-concerns --outcome success`.
6. **Checkpoint**: `uv run maverick task-progress set <repo>  tasks`.

## Phase 4: Create Worktree + Branch

This phase has changed in the overhaul. The branch is created **inside a
dedicated worktree**, not in the main checkout.

1. Derive the branch name per the mav-github-issue-workflow skill.
2. Resolve the base branch from the project config:
   ```bash
   STORY_BASE=$(uv run maverick git-workflow story-base)
   ```
   - If this story depends on a sibling story whose PR is open but not
     merged, stack per `mav-stacked-prs` — base = sibling branch.
3. Create the worktree: `uv run maverick worktree create <branch> [--base <sibling-branch>]`.
   From this point on, all file edits happen inside the worktree path.
4. `cd` into the worktree path for the rest of the story.
5. Update phase to `branch` in the state file.
6. **Checkpoint**: `uv run maverick task-progress set <repo>  branch`.

## Phase 5: Execute Tasks (push after every task)

This phase has changed. **Push after every task, not at the end.** See
`mav-durability-on-gh`.

1. Read project-level skills at `docs/maverick/skills/`. Apply any
   topic-specific guidance they carry.
2. Update phase to `implement` in the state file.

**For each task (sub-issue or checklist item), in order:**

Each step below is its own obligation. After `/do-code` returns
in step 2, **do not stop** — continue with step 3. The inner skill's
return is a hand-back, not a task-complete signal (#106).

1. **Open the `skill-dispatch` interval for `do-code`.** This
   pins the project's coding standards before any edit and gives the
   workflow report a `skill-dispatch` row for the task:
   ```bash
   uv run maverick report begin skill-dispatch --issue  \
       --phase implement --skill-name do-code
   ```
2. **Invoke `/do-code <one-line task description>`.** The
   skill reads before writing, makes the smallest diff that satisfies
   the task, verifies per `mav-local-verification`, and
   refuses to return on red. When it returns, proceed to step 3 — do
   not summarise and stop.
3. **Close the `skill-dispatch` interval** with the outcome:
   ```bash
   uv run maverick report end skill-dispatch --issue  \
       --phase implement --skill-name do-code \
       --outcome <success|failure>
   ```
   On `failure`, halt the per-task loop and diagnose per
   `mav-systematic-debugging` — do not proceed to the
   commit step with a failing build or red tests.
4. **(Optional) Sibling-dispatch `/do-test`** if the change
   needs new or updated tests that `do-code` did not
   already cover. Same three-step shape as above:
   ```bash
   uv run maverick report begin skill-dispatch --issue  \
       --phase implement --skill-name do-test
   # Invoke /do-test <unit|integration>
   uv run maverick report end skill-dispatch --issue  \
       --phase implement --skill-name do-test \
       --outcome <success|failure>
   ```
   When `/do-test` returns, proceed to step 5.
5. **Create a conventional commit** referencing the issue number.
6. **Push immediately.**
   - If this is the first push on the branch, set upstream:
     `git push -u origin <branch>`.
   - If on a stacked branch, run the retarget check per
     `mav-stacked-prs` **before every push**.
7. **Log the commit** to the workflow report. SHA and subject come from
   git; the timestamp is wall-clock at the moment of this CLI call:
   ```bash
   SHA=$(git rev-parse HEAD)
   SUBJECT=$(git log -1 --pretty=%s)
   uv run maverick report commit --issue  \
       --phase implement --sha "$SHA" --subject "$SUBJECT"
   ```
8. **Update the tasks comment** (or close the sub-issue).
9. **Heartbeat:** `uv run maverick coord heartbeat <repo> ` if
   it is time for a refresh.

After the last task, run the full verification suite once more.

**Checkpoint**: `uv run maverick task-progress set <repo>  implement`.

Follow `mav-plan-execution` for the broader execution loop,
verification discipline, failure handling, and crash recovery.

## Phase 6: Documentation Review (mandatory)

This phase **always runs** before the PR is opened. There is no skip
path — the heuristic-gated version used to let stale docs ship when
Claude's affected-or-not call was wrong. The agent decides whether
work is needed; the workflow decides whether the agent runs.

The agent is dispatched with a **pre-filtered shortlist** of docs the
diff plausibly touches, not the open-ended "audit every doc" brief
that made this phase the longest single subagent cost on prior issues
(observed: ~6 min on a 15-file diff). The agent still reports any
out-of-shortlist docs it believes are impacted — those surface in the
PR body as a follow-up note rather than being silently rewritten.

1. Compute the diff and changed paths:

   ```bash
   BASE=$(uv run maverick git-workflow story-base)
   git diff "origin/${BASE}...HEAD" > /tmp/diff.patch
   git diff --name-only "origin/${BASE}...HEAD" > /tmp/changed-paths.txt
   ```

2. **Build the candidate doc shortlist.** Derive search terms from the
   diff (basenames + top-level directories from changed paths, plus
   identifier-like tokens introduced or removed in added/removed lines).
   Grep every `docs/` tree in the repo. The shortlist may legitimately
   be empty — that is a valid input to step 3.

   ```bash
   {
     cut -d/ -f1 /tmp/changed-paths.txt
     sed 's|.*/||; s|\.[^.]*$||' /tmp/changed-paths.txt
     grep -E '^[+-][^+-]' /tmp/diff.patch \
       | grep -Eo '\b(function|def|class|interface|type|const|export)[[:space:]]+[A-Za-z_][A-Za-z0-9_]+' \
       | awk '{print $NF}'
   } | awk 'length($0) >= 3' | sort -u > /tmp/doc-terms.txt

   mapfile -t DOC_ROOTS < <(find . -type d -name docs \
     -not -path '*/node_modules/*' -not -path '*/.git/*' -not -path '*/.venv/*')

   : > /tmp/doc-shortlist.txt
   if [[ ${#DOC_ROOTS[@]} -gt 0 && -s /tmp/doc-terms.txt ]]; then
     while IFS= read -r term; do
       grep -rlF -- "$term" "${DOC_ROOTS[@]}" 2>/dev/null || true
     done < /tmp/doc-terms.txt \
       | grep -E '\.(md|mdx)$' \
       | sort -u > /tmp/doc-shortlist.txt
   fi
   ```

3. Open the agent-dispatch interval. The agent operates under `do-docs` — pass it as `--skill-name` so the Maverick Skill column in the report names the inner skill: `uv run maverick report begin agent-dispatch --issue  --phase docs --agent agent-tech-docs-writer --skill-name do-docs`.
4. Dispatch **agent-tech-docs-writer** with:
   - **Mode:** `update` (per `do-docs`)
   - **Diff:** `/tmp/diff.patch`
   - **Candidate docs:** the contents of `/tmp/doc-shortlist.txt`. If
     the file is empty, pass the literal string
     `<empty — scan only for gaps requiring new coverage>`.
   - **Instructions:**
     - Read each candidate doc. Update only sections rendered stale by
       the diff; do **not** refactor unrelated content.
     - If the diff introduces a component, subsystem, or architectural
       change with no coverage anywhere in `docs/`, create the new
       document.
     - If you find a doc **outside the candidate list** that you
       believe is impacted, **list its path in your return payload —
       do not edit it.** One-pass dispatch: no widen-and-retry; the
       caller folds these into a follow-up note on the PR for the
       human reviewer.
     - Returning "no doc changes required" is a valid outcome and must
       be reported explicitly (not silently inferred).
5. Close the agent-dispatch interval: `uv run maverick report end agent-dispatch --issue  --phase docs --agent agent-tech-docs-writer --skill-name do-docs --outcome success`.
6. **Record the outcome** in the PR body or as a one-line PR comment so
   the gate is auditable:
   - If docs were updated or created: list the files changed.
   - If the agent flagged out-of-shortlist docs: append a
     `Docs follow-up: <paths>` line to the PR body so the reviewer
     sees them.
   - If no changes were required: post `Docs review: no changes required.`
7. Commit any doc changes with a `docs:` conventional commit and push
   per the push-per-task rule. If a commit was made, log it so the
   docs phase row gets its own sub-row in the report:
   ```bash
   SHA=$(git rev-parse HEAD)
   SUBJECT=$(git log -1 --pretty=%s)
   uv run maverick report commit --issue  \
       --phase docs --sha "$SHA" --subject "$SUBJECT"
   ```
8. The PR cannot proceed to Phase 7 until this phase has produced
   either committed doc changes or the auditable no-op record.
9. **Checkpoint**: `uv run maverick task-progress set <repo>  docs`.

## Phase 7: Pre-push Cybersecurity Review (mandatory)

This phase **always runs** before the PR is opened. There is no skip
path. Any changed code AND any code that could be impacted by the
changes (callers, importers, dependents) must be reviewed by
`do-cybersecurity-review` before the PR can be opened.

Each step below is its own obligation. After `/do-cybersecurity-review`
returns in step 3, **do not stop** — continue with step 4. The inner
skill's return is a hand-back, not a phase-complete signal (#106).

1. **Compute the full diff:** `git diff origin/<base>...HEAD`.
2. **Open the `skill-dispatch` interval** for the review:
   `uv run maverick report begin skill-dispatch --issue  --phase security --skill-name do-cybersecurity-review`.
3. **Dispatch `/do-cybersecurity-review`** with:
   - **Mode:** `update`
   - **Diff:** the output of step 1, passed via stdin or as a file path
   - **Instructions:** review the changed code AND the impact set
     (callers, importers, dependents — bounded to one or two hops).
     Return the structured outcome (verdict + findings) defined in the
     skill's Update Mode contract.

   When the skill returns, proceed to step 4 — do not summarise and
   stop.
4. **Close the `skill-dispatch` interval** with the outcome:
   `uv run maverick report end skill-dispatch --issue  --phase security --skill-name do-cybersecurity-review --outcome <success|failure|blocked>` (use `blocked` if the verdict was BLOCKING).
5. **Act on the verdict:**
   - **BLOCKING** — halt. Surface the findings to the user verbatim.
     Do not open the PR. The user resolves the BLOCKING items by
     returning to Phase 5 (implement, test, commit, push). Re-run
     this phase against the new diff before proceeding.
   - **FINDINGS** — append a `## Security Review` section to the PR
     body draft listing each finding (severity, location, description,
     recommendation). The PR may proceed to Phase 8 with these items
     visible to the human reviewer and to agent-code-reviewer.
   - **PASS** — record `Security review: no concerns.` in the PR body
     draft so the gate is auditable.
6. The PR cannot proceed to Phase 8 until this phase has returned a
   non-BLOCKING verdict and the outcome has been folded into the PR
   body draft.

## Phase 8: Open PR + Monitor CI

1. Pre-push verification per `mav-local-verification` — a final
   green check before asking for review.
2. Stacked-PR retarget check per `mav-stacked-prs` if the branch
   stacks on a sibling. Retarget before opening the PR if the sibling is now
   merged.
3. Resolve the PR target from config:
   ```bash
   PR_TARGET=$(uv run maverick git-workflow pr-target)
   ```
   Open the PR. The body **must** end with a literal `Closes #`
   line (capitalised; not `Refs`, `Related to`, or any other phrasing).
   `gh pr merge --squash` carries the PR body verbatim into the squash
   commit body; GitHub only auto-closes the linked issue when one of
   `Closes`/`Fixes`/`Resolves` appears in a commit on the default
   branch. If multiple PRs land via a non-squash promotion (Gitflow:
   `develop` → `main`), each squash commit's body is what GitHub scans
   — so omitting the keyword on a single PR leaves *that* story open
   even after promotion (#56). Use `Refs #N` only for cross-references
   to *other* issues, never for the primary story:
   ```bash
   gh pr create --base "$PR_TARGET" --head <branch> \
       --title "<conventional title referencing #>" \
       --body "$(cat <<'PR_EOF'
   ## Summary
   <1-3 bullet points>

   Closes #
   PR_EOF
   )"
   ```
4. **Checkpoint**: `uv run maverick task-progress set <repo>  pr_open`.
5. Monitor CI per `mav-bp-cicd`. If CI fails, read logs, fix
   locally, push. Do not proceed to Phase 9 until CI is green.
6. **Browser/UI verification is non-blocking.** If the change touches UI
   and Claude's global instructions or a project skill ask for browser
   verification, run it with a strict timeout (e.g. 5 min total). On
   hang, timeout, or failure, post the outcome as a non-blocking PR
   comment and proceed to Phase 9 — do **not** wait indefinitely (#41).
   Phase 9's reviewer is the binding gate; CI is the binding regression
   check; ad-hoc browser runs are advisory.
7. **Checkpoint**: `uv run maverick task-progress set <repo>  ci_green`.

## Phase 9: Code Review (binary, hard gate)

The local **agent-code-reviewer** subagent's verdict is the
review gate the auto-merge path trusts. This is a binary verdict against
the open PR, not a local-diff advisory loop.

1. Open the agent-dispatch interval: `uv run maverick report begin agent-dispatch --issue  --phase review --agent agent-code-reviewer --skill-name mav-bp-code-review`.
2. Dispatch **agent-code-reviewer** with:
   - The PR URL
   - The issue body, design comment, and tasks list (so it has the spec)
3. Close the agent-dispatch interval: `uv run maverick report end agent-dispatch --issue  --phase review --agent agent-code-reviewer --skill-name mav-bp-code-review --outcome <success|failure>` (use `failure` on FAIL verdict).
4. The agent returns exactly one of two verdicts:
   - **PASS** — proceed to Phase 10 (merge).
   - **FAIL** — proceed to Phase 11 (eject). Do not attempt to auto-fix.
5. Update phase to `review` in the state file.
6. **Checkpoint**: `uv run maverick task-progress set <repo>  review`.

There is no fix-and-re-review loop. If the reviewer FAILs the PR, the
next step is eject-to-human, not iterate.

## Phase 10: Auto-merge (on PASS)

1. **Verify the PR body still carries the closing keyword.** The body
   becomes the squash commit body, and the closing keyword must survive
   into the commit that lands on the default branch (#56). If the body
   was edited after Phase 8 — by a reviewer, by another subagent, or by
   a force-push — re-add the line before merging:
   ```bash
   uv run maverick gh-app gh -- pr view <pr-url> --json body -q .body \
       | grep -Eq '(Closes|Fixes|Resolves) #\b' \
       || { echo "PR body missing 'Closes #' — re-add before merging"; exit 1; }
   ```
2. The Maverick GitHub App posts the approval:
   ```bash
   uv run maverick gh-app gh -- pr review <pr-url> --approve \
       --body "Approved by agent-code-reviewer at $(date -u +%FT%TZ)"
   ```
3. Enable auto-merge (squash):
   ```bash
   uv run maverick gh-app gh -- pr merge <pr-url> --auto --squash
   ```
   The merge waits on whatever required status checks the project's
   branch protection enforces — typically lint, tests, build, and (if
   the optional `mav-bp-remote-code-review` workflow is
   adopted) the CI-side re-run of agent-code-reviewer. If all required
   checks were already green, GitHub merges immediately; otherwise it
   merges when they pass.
4. **Wait for the merge to land** before continuing — poll
   `gh pr view <pr-url> --json state -q .state` until it reports
   `MERGED`. Cleanup steps below assume the PR is no longer in flight.
5. **Checkpoint**: `uv run maverick task-progress set <repo>  merged`.
6. Post the completion comment on the issue per
   `mav-github-issue-workflow`.
7. **Run the post-merge issue-lifecycle step.** This always posts an
   audit comment ("Resolved in PR #<P>; merged to <branch>.") and
   applies a `merged-to-<branch>` label, then closes the issue per the
   per-project policy in `.maverick/config.json`'s
   `issue_lifecycle.close_policy` (#52). The default policy
   (`on_pr_merge`) closes the issue immediately, which is right for
   trunk-based and GitHub Flow repos. Repos using Gitflow or custom
   promotion gates can set the policy to `on_default_branch_merge` or
   `manual` to keep the issue open until promotion — the audit comment
   and label still surface the merge so `gh issue list -l merged-to-develop`
   finds work pending promotion. The CLI is idempotent (re-running it
   on a closed issue is a no-op), so it is safe to retry:
   ```bash
   uv run maverick issue close-on-merge <repo>  \
       --pr <pr-num> --target <target-branch>
   ```
8. Update phase to `complete` in the state file.
9. Release the claim: `uv run maverick coord release <repo>  --reason merged`.
10. Clean up:
    - Local state file
    - Destroy the worktree: `uv run maverick worktree destroy <worktree-path>`.
11. **Checkpoint**: `uv run maverick task-progress set <repo>  complete`.
12. **Emit per-phase narrative notes** so the report's Analysis section
    has context for what happened. The JSONL is the authoritative
    record; the report is a pure render of it, so notes must land in
    the JSONL — do not edit the rendered Markdown by hand:
    ```bash
    uv run maverick report note --issue  --phase design \
        --text "<one-sentence summary of what the analyst returned>"
    uv run maverick report note --issue  --phase implement \
        --text "<one-sentence summary of what landed in Phase 5>"
    # ... one `report note` per phase that produced work worth narrating
    ```
13. **Generate the workflow report**. Written to the **main repo's**
    `.maverick/reports/` (resolved via `git rev-parse --git-common-dir`),
    not the destroyed worktree's. Re-runs are deterministic:
    ```bash
    uv run maverick report generate <repo> 
    ```

## Phase 11: Eject (on FAIL)

1. Post the reviewer's verdict as a PR comment (App identity, per
   `mav-github-issue-workflow`):
   ```bash
   uv run maverick gh-app gh -- pr comment <pr-url> --body-file /tmp/review-verdict.md
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
5. **Checkpoint the eject** (#83): `uv run maverick task-progress set <repo>  ejected`.
6. **Emit per-phase narrative notes** so the eject report has context
   for the human reviewer:
   ```bash
   uv run maverick report note --issue  --phase review \
       --text "<one-sentence summary of what the reviewer flagged>"
   # ... one `report note` per phase that produced work worth narrating
   ```
7. **Generate the workflow report**. Do this **before** releasing the
   claim so the report lands even if release errors:
   ```bash
   uv run maverick report generate <repo> 
   ```
8. Release the claim: `uv run maverick coord release <repo>  --reason ejected`.
9. Do **not** destroy the worktree — the human may want to inspect it.
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

<!-- maverick-plugin-version: 3.3.6 -->

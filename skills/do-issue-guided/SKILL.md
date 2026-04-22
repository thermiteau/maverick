---
name: do-issue-guided
description: Work on a GitHub issue interactively with the user. Proceeds autonomously through routine work but pauses for confirmation at key decision points and when uncertain.
argument-hint: issue number (e.g., 123)
user-invocable: true
disable-model-invocation: false
---

**Depends on:** mav-scope-boundaries, mav-git-workflow, mav-github-issue-workflow, mav-create-solution-design, mav-create-tasks, mav-plan-execution, mav-local-verification, mav-bp-cicd, mav-claude-code-recovery, mav-bp-logging, mav-bp-alerting, mav-systematic-debugging, do-pullrequest-review

# Work on GitHub Issue (Guided)

Work on GitHub issue `` interactively. Follow every phase in order. Do not skip phases. Proceed autonomously through routine work, but pause for user confirmation at key decision points marked with **🔲 Checkpoint**.

## Before You Begin

If `` is empty or not a valid issue number, ask the user for the issue number before proceeding. Do not attempt any phase without it.

## Phase 1-2: Understand the Issue and Solution Design (subagent)

Run Phases 1 and 2 as a subagent to keep the main context window clean for implementation.

1. Initialise the issue state file per the mav-github-issue-workflow skill.
2. Dispatch the **agent-issue-analyst** agent with:
   - Issue number: ``
   - Mode: `guided`
3. When the agent returns, verify:
   - `.claude/issue-state.json` has `phase` set to `design`
   - `.claude/issue-state.json` has `comments.design` set to a comment ID
4. If the agent flagged ambiguities, present them to the user and wait for answers before continuing.

**🔲 Checkpoint — Design review:** Present a brief summary of the solution design to the user. Include the key approach, main components affected, and any trade-offs. Ask the user to confirm or suggest changes before proceeding. Do not continue until the user approves.

## Phase 3: Create Tasks (subagent)

Run Phase 3 as a subagent to keep the main context window clean for implementation.

1. Dispatch the **agent-github-issue-planner** agent with:
   - Issue number: ``
   - Design comment ID from `.claude/issue-state.json`
2. When the agent returns, verify:
   - `.claude/issue-state.json` has `phase` set to `tasks`
   - If < 5 tasks: `.claude/issue-state.json` has `comments.tasks` set to a comment ID
   - If >= 5 tasks: `.claude/issue-state.json` has `has_sub_issues` set to `true`
3. If the agent flagged scope concerns, present them to the user.

**🔲 Checkpoint — Tasks review:** Present the task list to the user — each task title and description, their order, and any dependencies. Ask the user to confirm, reorder, add, or remove tasks. Do not continue until the user approves.

## Phase 4: Create Branch

1. Derive the branch name per the mav-github-issue-workflow skill (branching conventions).
2. Create the branch from the project's default branch (typically `main`).
3. Update phase to `branch` in the state file.

## Phase 5: Execute Tasks

1. Check for project-level skills in `docs/maverick/skills/`. For each topic directory that contains a `SKILL.md`, read it. These project skills provide codebase-specific guidance (libraries, patterns, configuration) that supplements the best-practice skills. If none exist, continue without them.
2. Update phase to `implement` in the state file.

**If `.claude/issue-state.json` has `has_sub_issues: true`:**

1. Read the tasks summary comment on the parent issue for the execution order
2. For each sub-issue in execution order:
   1. Read the sub-issue description
   2. Implement the change described
   3. Run verification (lint, typecheck, tests) per the mav-local-verification skill
   4. Commit with a conventional commit referencing the parent issue
   5. Update the tasks summary comment: mark the sub-issue as complete
   6. Close the sub-issue
3. After all sub-issues are complete, run the full verification suite

**Otherwise (checklist tasks):**

1. Read the tasks comment on the issue
2. For each task in order:
   1. Implement the change described
   2. Run verification (lint, typecheck, tests) per the mav-local-verification skill
   3. Commit with a conventional commit referencing the issue number
   4. Update the tasks comment: check off the completed task (`- [ ]` to `- [x]`)
3. After all tasks are complete, run the full verification suite

Follow the mav-plan-execution skill for the execution loop, verification discipline, failure handling, and crash recovery. In guided mode, it will:
- Provide brief progress checkpoints every 3-4 tasks.
- Pause and ask the user when uncertain about an implementation approach.
- Pause and discuss with the user when a design assumption proves wrong.
- Ask the user for help immediately when a task fails after 2 fix attempts.

## Phase 6: Code Review

1. Dispatch the agent-code-reviewer agent with the issue requirements and the diff (`git diff main...HEAD`).
2. The reviewer performs two-stage review: spec compliance first, then code quality.
3. If spec compliance fails, stop — fix the gaps before requesting re-review.
4. Process code quality feedback per the do-pullrequest-review skill:
   - Read all items before acting.
   - Clarify unclear items before implementing any.
   - Verify each suggestion against the codebase.
   - Push back with reasoning when a suggestion is incorrect.
   - Implement valid fixes one at a time, verifying after each.
5. If fixes changed the implementation approach, update the tasks comment on the issue.
6. Request re-review if there were critical or spec compliance issues. Repeat until approved.
7. Update phase to `review` in the state file.

**🔲 Checkpoint — Review results:** Present a summary of the review outcome to the user — what was flagged, what was fixed, and what was pushed back on. If there were significant changes during review, highlight them.

## Phase 7: Documentation Review

1. Run `git diff main...HEAD --name-only` to identify all changed files.
2. Determine whether the changes affect behaviour that is covered by existing documentation in `docs/`:
   - Changed or added public APIs, components, services, or configuration
   - Altered data flows, integration points, or architectural patterns
   - Modified feature behaviour described in existing docs
3. If documentation updates are needed, dispatch the **agent-tech-docs-writer** agent with:
   - Mode: **update**
   - The diff (`git diff main...HEAD`)
   - The list of affected doc files (or a note that new documentation is needed)
   - Instruction to update existing docs to reflect the changes — not to rewrite unrelated sections
4. Review the agent's output. Verify that updates are accurate and scoped to the changes made.
5. If no existing documentation is affected and the changes do not warrant a new document, skip this phase.

## Phase 8: Push and Verify CI

1. Run pre-push verification per the mav-local-verification skill (lint, typecheck, tests). Fix any failures before pushing.
2. Push the branch to remote.
3. Monitor CI status per the mav-bp-cicd skill. If CI fails, read the failure logs, fix locally, and push again. Do not proceed until CI passes.

## Phase 9: Update Issue and Create PR

1. Post a completion comment on the issue per the mav-github-issue-workflow skill (post completion comment pattern).
2. Create a pull request per the mav-github-issue-workflow skill (PR pattern).
3. Update phase to `complete` in the state file.
4. Clean up the state file.

**🔲 Checkpoint — Done:** Present the PR URL to the user and summarise what was delivered.

## Rules

- **Pause at checkpoints** — every phase marked with 🔲 requires user confirmation before continuing.
- **Work autonomously between checkpoints** — do not ask for permission on routine implementation work. Only ask when uncertain, blocked, or at a checkpoint.
- **Run verification** after each task and after all tasks. Do not declare success if checks fail.
- **Never commit directly** to `main`.
- **Use conventional commits** that reference the issue number (e.g., `feat: add rubric export (#42)`).
- **Always create a PR** at the end — deliver a complete result.

<!-- maverick-plugin-version: 0.5.8-dev -->

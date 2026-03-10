---
name: do-issue-solo
description: Work on a GitHub issue end-to-end autonomously, only pausing when blocked or when clarification is needed.
argument-hint: issue number (e.g., 123)
user-invocable: true
disable-model-invocation: false
---

**Depends on:** mav-scope-boundaries, mav-git-workflow, mav-github-issue-workflow, create-solution-design, create-implementation-plan, task-breakdown, mav-plan-execution, mav-local-verification, mav-bp-cicd, mav-claude-code-recovery, mav-bp-logging, mav-bp-alerting, mav-systematic-debugging, pullrequest-review

# Work on GitHub Issue (Autonomous)

Work on GitHub issue `$ARGUMENTS` autonomously. Follow every phase in order. Do not skip phases. Only pause to ask the user when you are blocked or need clarification.

## Before You Begin

If `$ARGUMENTS` is empty or not a valid issue number, ask the user for the issue number before proceeding. Do not attempt any phase without it.

## Phase 1-2: Understand the Issue and Solution Design (subagent)

Run Phases 1 and 2 as a subagent to keep the main context window clean for implementation.

1. Initialise the issue state file per the mav-github-issue-workflow skill.
2. Dispatch the **issue-analyst** agent with:
   - Issue number: `$ARGUMENTS`
   - Mode: `solo`
3. When the agent returns, verify:
   - `.claude/issue-state.json` has `phase` set to `design`
   - `.claude/issue-state.json` has `comments.design` set to a comment ID
4. If the agent flagged ambiguities it could not resolve, ask the user. Otherwise continue.

## Phase 3: Implementation Plan (subagent)

Run Phase 3 as a subagent to keep the main context window clean for implementation.

1. Dispatch the **issue-planner** agent with:
   - Issue number: `$ARGUMENTS`
   - Design comment ID from `.claude/issue-state.json`
2. When the agent returns, verify:
   - `.claude/issue-state.json` has `phase` set to `plan`
   - `.claude/issue-state.json` has `comments.plan` set to a comment ID
3. If the agent flagged scope concerns, ask the user. Otherwise continue.

## Phase 3.5: Evaluate Plan Scope

After receiving the plan from the issue-planner agent:

1. Read the plan comment and count the steps
2. If steps <= 8: proceed to Phase 4 (no breakdown needed)
3. If steps > 8: invoke the task-breakdown skill
   - Input: task ID (issue number), plan comment ID, design comment ID, mode: `issue`
   - Verify: sub-issues are created and breakdown comment is posted on the parent issue
   - Update `.claude/issue-state.json`: `has_sub_tasks` = `true`
4. Continue to Phase 4

## Phase 4: Create Branch

1. Derive the branch name per the mav-github-issue-workflow skill (branching conventions).
2. Create the branch from the project's integration branch (typically `develop`).
3. Update phase to `branch` in the state file.

## Phase 5: Execute the Plan

1. Check for project-level skills in `docs/maverick/skills/`. For each topic directory that contains a `SKILL.md`, read it. These project skills provide codebase-specific guidance (libraries, patterns, configuration) that supplements the best-practice skills. If none exist, continue without them.
2. Update phase to `implement` in the state file.

**If `.claude/issue-state.json` has `has_sub_tasks: true`:**

1. Read the breakdown comment on the parent issue for `execution_order`
2. For each sub-issue in `execution_order`:
   1. Read the sub-issue's plan comment
   2. Execute the sub-issue's steps using the mav-plan-execution skill
   3. After all steps complete, update the breakdown comment: set status to `"complete"`
   4. Close the sub-issue
3. After all sub-issues complete, run the full verification suite

**Otherwise (no sub-tasks):**

1. Follow the mav-plan-execution skill to execute each step.
2. The plan-execution skill handles: step-by-step implementation, verification, failure handling, progress tracking, crash recovery, and acceptance criteria checking.
3. In solo mode, it will work autonomously — only pausing when genuinely blocked.

## Phase 6: Code Review

1. Dispatch the code-reviewer agent with the issue requirements and the diff (`git diff develop...HEAD`).
2. The reviewer performs two-stage review: spec compliance first, then code quality.
3. If spec compliance fails, stop — fix the gaps before requesting re-review.
4. Process code quality feedback per the pullrequest-review skill:
   - Read all items before acting.
   - Clarify unclear items before implementing any.
   - Verify each suggestion against the codebase.
   - Push back with reasoning when a suggestion is incorrect.
   - Implement valid fixes one at a time, verifying after each.
5. If fixes changed the implementation approach, update the plan comment on the issue.
6. Request re-review if there were critical or spec compliance issues. Repeat until approved.
7. Update phase to `review` in the state file.

## Phase 7: Documentation Review

1. Run `git diff develop...HEAD --name-only` to identify all changed files.
2. Determine whether the changes affect behaviour that is covered by existing documentation in `docs/`:
   - Changed or added public APIs, components, services, or configuration
   - Altered data flows, integration points, or architectural patterns
   - Modified feature behaviour described in existing docs
3. If documentation updates are needed, dispatch the **tech-docs-writer** agent with:
   - Mode: **update**
   - The diff (`git diff develop...HEAD`)
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

## Rules

- **Only pause for user input** when blocked or when the issue is ambiguous. Do not ask for approval on design or plan unless you are uncertain.
- **Run verification** after each step and after all steps. Do not declare success if checks fail.
- **Never commit directly** to `main` or `develop`.
- **Use conventional commits** that reference the issue number (e.g., `feat: add rubric export (#42)`).
- **Always create a PR** at the end — this is the autonomous workflow, so deliver a complete result.

---
name: do-issue-solo
description: Work on a GitHub issue end-to-end autonomously, only pausing when blocked or when clarification is needed.
argument-hint: issue number (e.g., 123)
disable-model-invocation: false
user-invocable: true
---

**Depends on:** scope-boundaries, git-workflow, github-issue-workflow, solution-design, implementation-plan, plan-execution, local-verification, ci-awareness, claude-code-recovery, logging-bestpractice, alerting-bestpractice, systematic-debugging, verification-before-completion, receiving-code-review

# Work on GitHub Issue (Autonomous)

Work on GitHub issue `$ARGUMENTS` autonomously. Follow every phase in order. Do not skip phases. Only pause to ask the user when you are blocked or need clarification.

## Phase 1: Understand the Issue

1. Initialise the issue state file per the github-issue-workflow skill.
2. Read the full issue:
   ```
   gh issue view $ARGUMENTS --json title,body,labels,assignees,milestone,comments,state
   ```
3. Summarise the issue in 3-5 bullet points: what is being requested, why it matters, and any constraints or acceptance criteria.
4. If the issue is ambiguous or missing critical information, ask the user. Otherwise continue.
5. Update phase to `understand` in the state file.

## Phase 2: Solution Design

1. Follow the solution-design skill to explore the codebase and produce a design.
2. If you cannot produce a design without user input, ask. Otherwise continue.
3. Post the design as a comment on the issue per the github-issue-workflow skill (post design comment pattern).
4. Update phase to `design` in the state file.

## Phase 3: Implementation Plan

1. Follow the task-decomposition skill to break the design into ordered implementation steps.
2. If you cannot decompose without user input, ask. Otherwise continue.
3. Post the plan as a comment on the issue per the github-issue-workflow skill (post plan comment pattern).
4. Update phase to `plan` in the state file.

## Phase 4: Create Branch

1. Derive the branch name per the github-issue-workflow skill (branching conventions).
2. Create the branch from the project's integration branch (typically `develop`).
3. Update phase to `branch` in the state file.

## Phase 5: Execute the Plan

1. Follow the plan-execution skill to execute each step.
2. The plan-execution skill handles: step-by-step implementation, verification, failure handling, progress tracking, crash recovery, and acceptance criteria checking.
3. In solo mode, it will work autonomously — only pausing when genuinely blocked.
4. Update phase to `implement` in the state file.

## Phase 6: Code Review

1. Dispatch the code-reviewer agent with the issue requirements and the diff (`git diff develop...HEAD`).
2. The reviewer performs two-stage review: spec compliance first, then code quality.
3. If spec compliance fails, stop — fix the gaps before requesting re-review.
4. Process code quality feedback per the receiving-code-review skill:
   - Read all items before acting.
   - Clarify unclear items before implementing any.
   - Verify each suggestion against the codebase.
   - Push back with reasoning when a suggestion is incorrect.
   - Implement valid fixes one at a time, verifying after each.
5. If fixes changed the implementation approach, update the plan comment on the issue.
6. Request re-review if there were critical or spec compliance issues. Repeat until approved.
7. Update phase to `review` in the state file.

## Phase 7: Push and Verify CI

1. Run pre-push verification per the local-verification skill (lint, typecheck, tests). Fix any failures before pushing.
2. Push the branch to remote.
3. Monitor CI status per the ci-awareness skill. If CI fails, read the failure logs, fix locally, and push again. Do not proceed until CI passes.

## Phase 8: Update Issue and Create PR

1. Post a completion comment on the issue per the github-issue-workflow skill (post completion comment pattern).
2. Create a pull request per the github-issue-workflow skill (PR pattern).
3. Update phase to `complete` in the state file.
4. Clean up the state file.

## Rules

- **Only pause for user input** when blocked or when the issue is ambiguous. Do not ask for approval on design or plan unless you are uncertain.
- **Run verification** after each step and after all steps. Do not declare success if checks fail.
- **Never commit directly** to `main` or `develop`.
- **Use conventional commits** that reference the issue number (e.g., `feat: add rubric export (#42)`).
- **Always create a PR** at the end — this is the autonomous workflow, so deliver a complete result.


**Depends on:** $DEPENDS_ON

# Work on GitHub Issue (Guided)

Work on GitHub issue `$ARGUMENTS` interactively. Follow every phase in order. Do not skip phases. Proceed autonomously through routine work, but pause for user confirmation at key decision points marked with **🔲 Checkpoint**.

## Before You Begin

If `$ARGUMENTS` is empty or not a valid issue number, ask the user for the issue number before proceeding. Do not attempt any phase without it.

## Phase 1-2: Understand the Issue and Solution Design (subagent)

Run Phases 1 and 2 as a subagent to keep the main context window clean for implementation.

1. Initialise the issue state file per the mav-github-issue-workflow skill.
2. Dispatch the **issue-analyst** agent with:
   - Issue number: `$ARGUMENTS`
   - Mode: `guided`
3. When the agent returns, verify:
   - `.claude/issue-state.json` has `phase` set to `design`
   - `.claude/issue-state.json` has `comments.design` set to a comment ID
4. If the agent flagged ambiguities, present them to the user and wait for answers before continuing.

**🔲 Checkpoint — Design review:** Present a brief summary of the solution design to the user. Include the key approach, main components affected, and any trade-offs. Ask the user to confirm or suggest changes before proceeding. Do not continue until the user approves.

## Phase 3: Implementation Plan (subagent)

Run Phase 3 as a subagent to keep the main context window clean for implementation.

1. Dispatch the **issue-planner** agent with:
   - Issue number: `$ARGUMENTS`
   - Design comment ID from `.claude/issue-state.json`
2. When the agent returns, verify:
   - `.claude/issue-state.json` has `phase` set to `plan`
   - `.claude/issue-state.json` has `comments.plan` set to a comment ID
3. If the agent flagged scope concerns, present them to the user.

**🔲 Checkpoint — Plan review:** Present the implementation plan to the user — the list of steps, their order, and the verification approach. Ask the user to confirm, reorder, add, or remove steps. Do not continue until the user approves.

## Phase 4: Create Branch

1. Derive the branch name per the mav-github-issue-workflow skill (branching conventions).
2. Create the branch from the project's integration branch (typically `develop`).
3. Update phase to `branch` in the state file.

## Phase 5: Execute the Plan

1. Check for project-level skills in `docs/maverick/skills/`. For each topic directory that contains a `SKILL.md`, read it. These project skills provide codebase-specific guidance (libraries, patterns, configuration) that supplements the best-practice skills. If none exist, continue without them.
2. Follow the mav-plan-execution skill to execute each step.
3. The plan-execution skill handles: step-by-step implementation, verification, failure handling, progress tracking, crash recovery, and acceptance criteria checking.
4. In guided mode, it will:
   - Provide brief progress checkpoints every 3-4 steps.
   - Pause and ask the user when uncertain about an implementation approach.
   - Pause and discuss with the user when a design assumption proves wrong.
   - Ask the user for help immediately when a step fails after 2 fix attempts.
5. Update phase to `implement` in the state file.

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

**🔲 Checkpoint — Review results:** Present a summary of the review outcome to the user — what was flagged, what was fixed, and what was pushed back on. If there were significant changes during review, highlight them.

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

**🔲 Checkpoint — Done:** Present the PR URL to the user and summarise what was delivered.

## Rules

- **Pause at checkpoints** — every phase marked with 🔲 requires user confirmation before continuing.
- **Work autonomously between checkpoints** — do not ask for permission on routine implementation work. Only ask when uncertain, blocked, or at a checkpoint.
- **Run verification** after each step and after all steps. Do not declare success if checks fail.
- **Never commit directly** to `main` or `develop`.
- **Use conventional commits** that reference the issue number (e.g., `feat: add rubric export (#42)`).
- **Always create a PR** at the end — deliver a complete result.

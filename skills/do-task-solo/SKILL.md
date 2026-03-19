---
name: do-task-solo
description: Work on a user-described task end-to-end autonomously using local task files instead of GitHub issues. The user describes what they want interactively, and Claude formalises, designs, plans, and implements it.
argument-hint: short task description (optional — will prompt if missing)
user-invocable: true
disable-model-invocation: false
---

**Depends on:** mav-scope-boundaries, mav-git-workflow, mav-create-solution-design, mav-create-tasks, mav-plan-execution, mav-local-verification, mav-bp-cicd, mav-claude-code-recovery, mav-bp-logging, mav-bp-alerting, mav-systematic-debugging, do-pullrequest-review

# Work on Task (Autonomous, Local)

Work on a user-described task autonomously. All artifacts (task description, solution design, tasks, progress) are stored locally under `.maverick/do-task/` instead of on GitHub. Follow every phase in order. Do not skip phases. Only pause to ask the user when you are blocked or need clarification.

## Before You Begin

1. If `` is empty, ask the user to describe what they want. Gather enough detail to write a clear task description — the outcome, any constraints, and acceptance criteria.
2. If `` is provided, use it as the starting point. If it is too vague to act on, ask the user for clarification before proceeding.

## Task File Structure

All task artifacts live under `.maverick/do-task/<TASK-ID>/`. The task ID is a zero-padded sequential number (e.g., `TASK-001`, `TASK-002`).

```
.maverick/do-task/
  TASK-001/
    task.md            # Formalised task description (the "issue")
    design.md          # Solution design
    tasks.md           # Task checklist
    state.json         # Phase and progress tracking
    completion.md      # Completion summary
```

### Initialise the Task Directory

```bash
mkdir -p .maverick/do-task

# Determine next task ID
LAST=$(ls -1 .maverick/do-task/ 2>/dev/null | grep '^TASK-' | sort -V | tail -1 | sed 's/TASK-0*//')
NEXT=$((${LAST:-0} + 1))
TASK_ID=$(printf "TASK-%03d" $NEXT)
TASK_DIR=".maverick/do-task/$TASK_ID"
mkdir -p "$TASK_DIR"
```

### Ensure Gitignore

Before creating any files, ensure the task state file is gitignored (task documents themselves are committed so they survive across sessions):

```bash
grep -q '.maverick/do-task/*/state.json' .gitignore 2>/dev/null || echo '.maverick/do-task/*/state.json' >> .gitignore
```

### State File

Maintain `state.json` to track progress across sessions. This file is gitignored.

```json
{
  "task_id": "TASK-001",
  "branch": null,
  "phase": "understand|design|tasks|branch|implement|review|complete",
  "created": "2026-03-10T12:00:00Z"
}
```

## Phase 1: Formalise the Task

Capture the user's request as a structured task document. This replaces the GitHub issue.

Write `.maverick/do-task/<TASK-ID>/task.md`:

```markdown
# <Concise task title>

## Description

<What the user wants, written clearly and completely. Include context, motivation, and any background the user provided.>

## Acceptance Criteria

- [ ] <Criterion 1 — specific, verifiable>
- [ ] <Criterion 2>
- [ ] <Criterion N>

## Constraints

<Any constraints mentioned by the user — performance, compatibility, scope limits, etc. Omit section if none.>

---
*Task ID: TASK-001 | Created: 2026-03-10*
```

Rules for formalising:
- Write acceptance criteria that are specific and testable. "It works" is not an acceptance criterion.
- If the user's description is ambiguous, ask for clarification before writing the task file.
- If the request is trivial (typo, config change), the task document can be brief — a title and one acceptance criterion is fine.

Update `state.json` phase to `understand`.

## Phase 2: Solution Design (subagent)

Run Phase 2 as a subagent to keep the main context window clean for implementation.

1. Dispatch the **agent-issue-analyst** agent with:
   - Task ID and path to `task.md` (instead of an issue number)
   - Mode: `solo`
   - Instruction to read the task from the local file and write the design to `.maverick/do-task/<TASK-ID>/design.md` instead of posting a GitHub comment
2. When the agent returns, verify:
   - `design.md` exists and follows the solution design structure (Approach, Areas Affected, Key Decisions, Risks, Acceptance Criteria Mapping)
   - `state.json` has `phase` set to `design`
3. If the agent flagged ambiguities it could not resolve, ask the user. Otherwise continue.

The design document follows the same structure as the mav-create-solution-design skill, written to `design.md` instead of a GitHub comment.

## Phase 3: Create Tasks (subagent)

Run Phase 3 as a subagent to keep the main context window clean for implementation.

1. Dispatch the **agent-task-planner** agent with:
   - Task ID and path to `design.md`
   - Instruction to read the design from the local file and write the task list to `.maverick/do-task/<TASK-ID>/tasks.md`
2. When the agent returns, verify:
   - `tasks.md` exists and contains a checkbox-format task list
   - `state.json` has `phase` set to `tasks`
3. If the agent flagged scope concerns, ask the user. Otherwise continue.

## Phase 4: Create Branch

1. Derive the branch name from the task. Use the format `<type>/<task-id>-<short-desc>` (e.g., `feat/TASK-001-add-export`). Follow the mav-git-workflow skill for type prefixes.
2. Create the branch from the project's integration branch (typically `develop`).
3. Commit the task artifacts (`task.md`, `design.md`, `tasks.md`) so they are tracked in version control.
4. Update `state.json`: set `branch` and `phase` to `branch`.

## Phase 5: Execute Tasks

1. Check for project-level skills in `docs/maverick/skills/`. For each topic directory that contains a `SKILL.md`, read it. These project skills provide codebase-specific guidance (libraries, patterns, configuration) that supplements the best-practice skills. If none exist, continue without them.
2. Update `state.json` phase to `implement`.

Read the task list from `tasks.md` and execute each task in order:

1. For each task:
   1. Implement the change described
   2. Run verification (lint, typecheck, tests) per the mav-local-verification skill
   3. Commit with a conventional commit referencing the task ID
   4. Update `tasks.md`: check off the completed task (`- [ ]` to `- [x]`) and commit the update
2. After all tasks are complete, run the full verification suite

Follow the mav-plan-execution skill for the execution loop, verification discipline, failure handling, and crash recovery. In solo mode, it will work autonomously — only pausing when genuinely blocked.

## Phase 6: Code Review

1. Dispatch the agent-code-reviewer agent with the task requirements (from `task.md`) and the diff (`git diff develop...HEAD`).
2. The reviewer performs two-stage review: spec compliance first, then code quality.
3. If spec compliance fails, stop — fix the gaps before requesting re-review.
4. Process code quality feedback per the do-pullrequest-review skill:
   - Read all items before acting.
   - Clarify unclear items before implementing any.
   - Verify each suggestion against the codebase.
   - Push back with reasoning when a suggestion is incorrect.
   - Implement valid fixes one at a time, verifying after each.
5. If fixes changed the implementation approach, update `design.md` and `tasks.md`.
6. Request re-review if there were critical or spec compliance issues. Repeat until approved.
7. Update `state.json` phase to `review`.

## Phase 7: Documentation Review

1. Run `git diff develop...HEAD --name-only` to identify all changed files.
2. Determine whether the changes affect behaviour that is covered by existing documentation in `docs/`:
   - Changed or added public APIs, components, services, or configuration
   - Altered data flows, integration points, or architectural patterns
   - Modified feature behaviour described in existing docs
3. If documentation updates are needed, dispatch the **agent-tech-docs-writer** agent with:
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

## Phase 9: Complete the Task

1. Write `.maverick/do-task/<TASK-ID>/completion.md`:

```markdown
# Completion: <Task title>

**Task ID:** TASK-001
**Branch:** `feat/TASK-001-add-export`

## Changes Made

- <Summary of what was implemented>

## Verification

- [x] Linting passes
- [x] Tests pass
- [x] Acceptance criteria met

## Acceptance Criteria Status

- [x] <Criterion 1> — implemented in <file/commit>
- [x] <Criterion 2> — implemented in <file/commit>

---
*Completed: 2026-03-10*
```

2. Commit the completion file and any final task document updates.
3. Update `state.json` phase to `complete`.
4. Create a pull request per the mav-git-workflow skill. Reference the task ID in the PR body:

```bash
gh pr create --title "<concise title>" --body "$(cat <<PR_EOF
## Summary
<1-3 bullet points>

Task: $TASK_ID (see \`.maverick/do-task/$TASK_ID/\`)

## Test Plan
- [ ] <verification steps>

---
*Created by Claude Code*
PR_EOF
)"
```

5. Present the PR URL to the user.

## Resuming Work

When resuming work on a task (new session, after crash):

1. Check `.maverick/do-task/` for any task with a `state.json` where `phase` is not `complete`.
2. If found — read the state, read the task artifacts, and resume from the recorded phase.
3. Cross-reference `tasks.md` checkboxes with `git log` to detect progress that wasn't recorded.
4. Resume from the first unchecked task.
5. If multiple incomplete tasks exist, ask the user which one to resume.
6. If no incomplete tasks exist and no arguments were given, ask the user what they want to do.

## Rules

- **Only pause for user input** when blocked or when the task is ambiguous. Do not ask for approval on design or tasks unless you are uncertain.
- **Run verification** after each task and after all tasks. Do not declare success if checks fail.
- **Never commit directly** to `main` or `develop`.
- **Use conventional commits** that reference the task ID (e.g., `feat: add rubric export (TASK-001)`).
- **Always create a PR** at the end — this is the autonomous workflow, so deliver a complete result.
- **Commit task artifacts** (`task.md`, `design.md`, `tasks.md`, `completion.md`) to version control so they are available for review and survive across sessions. Only `state.json` is gitignored.

<!-- maverick-plugin-version: 0.5.3 -->

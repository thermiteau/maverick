---
name: mav-bp-code-review
description: Code review conventions for all projects. Covers mandatory review requirements, review scope, PR sizing, reviewer and author responsibilities, and automated review integration. Applied when creating or reviewing pull requests.
---

# Code Review Standards

Ensure all code changes are reviewed before merging. Reviews catch defects, share knowledge, and maintain codebase quality. Optimise for small, focused pull requests with timely, constructive feedback.

## Principles

1. **All changes reviewed before merge** — no code reaches a protected branch without at least one approval from a reviewer who was not the author
2. **Small PRs get better reviews** — large diffs lead to superficial reviews. Keep pull requests focused and digestible.
3. **Review for correctness, security, and maintainability** — style issues are handled by linters, not humans
4. **Automated checks supplement, not replace, human review** — linting, type checking, and AI review catch mechanical issues; humans assess design, intent, and edge cases

## Mandatory Review Requirements

- **At least one approval** before merging to any protected branch (e.g., `main`)
- **No self-approvals** — the author cannot approve their own pull request
- **Stale approvals dismissed on new pushes** — if the author pushes new commits after approval, the approval is invalidated and a re-review is required
- **All CI checks passing** — do not merge with failing lints, tests, or type checks

## Review Scope

Every review should evaluate the change against these dimensions:

| Dimension          | What to check                                                                                         |
| ------------------ | ----------------------------------------------------------------------------------------------------- |
| **Correctness**    | Does the code do what it claims? Are edge cases handled? Are assumptions documented?                  |
| **Security**       | Are inputs validated? Are secrets exposed? Are auth checks present where needed? SQL injection, XSS?  |
| **Maintainability** | Is the code readable? Are names clear? Is complexity justified? Will the next developer understand it? |
| **Test coverage**  | Are new code paths tested? Are edge cases covered? Do tests actually assert meaningful outcomes?       |
| **Documentation**  | Are public APIs documented? Are non-obvious decisions explained? Is the PR description clear?          |

## Reviewer Responsibilities

- **Understand the change** — read the PR description, linked issue, and relevant context before reviewing code
- **Check edge cases** — think about what happens with empty inputs, nulls, concurrent access, large data sets, and failure modes
- **Be timely** — complete reviews within one business day (see Review SLA below)
- **Be constructive** — explain *why* something is a problem, not just that it is. Suggest alternatives.
- **Distinguish blocking from non-blocking** — prefix optional suggestions with "nit:" or "optional:" so the author knows what must be addressed
- **Approve when satisfied** — do not hold PRs hostage for perfection. If the code is correct, secure, and maintainable, approve it.

## Author Responsibilities

- **Self-review first** — review your own diff before requesting review. Catch obvious issues yourself.
- **Write clear descriptions** — explain what the PR does, why it is needed, and how to test it. Link the relevant issue.
- **Keep PRs small and focused** — one logical change per PR. Do not bundle unrelated changes.
- **Respond to feedback promptly** — address comments, push fixes, or explain your reasoning within one business day
- **Do not take feedback personally** — review comments are about the code, not the author

## PR Size Guidance

| Size              | Lines changed | Review quality | Recommendation                                |
| ----------------- | ------------- | -------------- | --------------------------------------------- |
| **Small**         | < 100         | Excellent      | Ideal. Aim for this size.                     |
| **Medium**        | 100 - 400     | Good           | Acceptable for most feature work.             |
| **Large**         | 400 - 800     | Declining      | Split if possible. Flag to reviewers.         |
| **Too large**     | > 800         | Poor           | Must split. Reviewers cannot effectively review this. |

### How to Split Large PRs

- **By layer** — separate backend and frontend changes
- **By feature slice** — implement one endpoint or one UI component per PR
- **By phase** — refactor first (separate PR), then add new functionality
- **By dependency** — extract shared utilities or models into a preparatory PR

## Review SLA

| Action                         | Target                    |
| ------------------------------ | ------------------------- |
| First review comment           | Within 1 business day     |
| Follow-up after author responds | Within 4 business hours   |
| Final approval                 | Within 2 business days of PR creation |

If a review will be delayed, communicate proactively. A quick "I'll review this tomorrow" is better than silence.

## Automated Review Integration

Automated tools handle mechanical checks so human reviewers can focus on design and logic:

| Tool                                         | What it catches                                      |
| -------------------------------------------- | ---------------------------------------------------- |
| **Linters**                                  | Style violations, unused imports, formatting          |
| **Type checkers**                            | Type mismatches, null safety, missing returns         |
| **Test suites**                              | Regressions, broken functionality                    |
| **AI code review** (agent-code-reviewer) | Spec compliance, common patterns, security smells    |

### Rules for Automated Reviews

- **Automated checks must pass before human review** — do not waste reviewer time on code that does not compile or pass lint
- **AI review findings require human judgement** — AI reviewers may flag false positives. The human reviewer makes the final call.
- **Do not disable checks to merge faster** — if a check is wrong, fix the check configuration, do not skip it

## What NOT to Review

Human review time is expensive. Do not spend it on issues that automated tools handle:

- **Style and formatting** — linters and formatters enforce this. Do not comment on brace placement, indentation, or trailing commas.
- **Personal preferences** — if both approaches are correct, readable, and maintainable, do not request a change to match your personal style
- **Trivial naming** — unless a name is actively misleading, do not bikeshed over whether `getData` should be `fetchData`
- **Generated code** — auto-generated files (protobuf, GraphQL codegen, lockfiles) do not need line-by-line review

## Detecting Code Review Anti-Patterns

| Pattern                                           | Issue                              | Fix                                                  |
| ------------------------------------------------- | ---------------------------------- | ---------------------------------------------------- |
| PR merged without any review                      | No review gate                     | Enable branch protection requiring approvals         |
| PR with 1000+ lines changed                       | Too large to review effectively    | Split into smaller, focused PRs                      |
| Review pending for 3+ business days               | SLA violation                      | Escalate or reassign reviewer                        |
| All review comments are style nits                 | Wasted review effort               | Configure linters to catch style; focus on logic     |
| Reviewer approves without comments on large PR     | Rubber-stamp review                | Reviewers must demonstrate understanding of the change |
| Author pushes "fix review" commits without context | Lost review trail                  | Explain what was changed in response to which comment |
| Self-approval on protected branch                  | Missing review gate                | Configure branch protection to disallow self-approval |
| Skipping CI to merge faster                        | Bypassing quality gates            | CI must pass; fix failures, do not skip them         |

<!-- maverick-plugin-version: 0.5.8-dev -->

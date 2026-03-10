---
title: Maverick Architecture
scope: Best practice workflows
relates-to:
last-verified: 2026-03-02
---

# Architecture

## Skills

Skills are markdown files with YAML frontmatter that load into the LLM's context window. They provide machine-readable guidance — dense, factual, and actionable.

| Category            | Skills                                                                             | Purpose                                                        |
| ------------------- | ---------------------------------------------------------------------------------- | -------------------------------------------------------------- |
| **Best Practices**  | logging, alerting, linting, unit-testing, cicd                                     | Define standards for each practice area                        |
| **Workflow**        | do-issue-solo, do-issue-guided, do-task-solo, create-solution-design, create-implementation-plan, task-breakdown | Orchestrate multi-step development workflows                   |
| **Execution**       | mav-plan-execution, mav-local-verification, subagents                              | Control how plans are executed and verified                    |
| **Git & GitHub**    | mav-git-workflow, mav-github-issue-workflow                                        | Define branching, commit, and issue interaction patterns       |
| **CI/CD Platforms** | mav-bp-cicd-github, mav-bp-cicd-gitlab, mav-bp-cicd-azure                         | Platform-specific pipeline monitoring                          |
| **Governance**      | mav-scope-boundaries, mav-claude-code-recovery, mav-systematic-debugging           | Define hard limits and resilience patterns                     |
| **Project Setup**   | upskill, maverick-alignment, tech-docs, pullrequest-review                         | Generate project skills, audit codebases, manage documentation |

### The Upskill System

Best-practice skills define universal standards. But every project is different - different languages, frameworks, libraries, and conventions. The **upskill** system bridges this gap:

```mermaid
flowchart TD
    UP["/upskill invoked"] --> SCAN["Scan codebase for each topic"]
    SCAN --> FOUND{"Implementation found?"}
    FOUND -->|"yes"| FULL["Write project skill from detected patterns"]
    FOUND -->|"no"| BP{"Best-practice skill exists?"}
    BP -->|"yes"| REC["Write recommended skill from best practices + project context"]
    BP -->|"no"| STUB["Write minimal stub"]
    FULL --> OUT["docs/maverick/skills/<topic>/SKILL.md"]
    REC --> OUT
    STUB --> OUT
```

- Scans the codebase for each topic defined in `skills/upskill/topics.json`
- If an implementation exists (e.g., Pino logger configured), documents exactly what's there
- If no implementation exists but a best-practice skill is available, generates a **recommended** implementation tailored to the project's stack
- Project skills are version-controlled and editable - the team can review and adjust recommendations

Default topics scanned: logging, alerting, unit-testing, integration-testing, linting, CI/CD.

### Agents

Agents are autonomous workers that run in isolated context windows. They verify code quality without human involvement.

| Agent                | Purpose                                                   | When it runs                            |
| -------------------- | --------------------------------------------------------- | --------------------------------------- |
| **Code Reviewer**    | Two-stage review: spec compliance, then code quality      | After implementation steps or before PR |
| **Backend Tester**   | Write and verify backend tests (Vitest, Fastify)          | After business logic implementation     |
| **Frontend Tester**  | Write and verify frontend tests (Vitest, Playwright, RTL) | After component implementation          |
| **Tech Docs Writer** | Generate technical documentation with Mermaid diagrams    | After significant architecture changes  |

Agents reference skills for domain knowledge but operate independently - they don't share the main session's context window.

### Workflow Entry Points

Maverick provides three primary workflows. Two are GitHub issue-driven, one is local task-driven:

```mermaid
flowchart TD
    SOURCE{"Work source?"}

    SOURCE -->|"GitHub issue"| ISSUEMODE{"Workflow mode?"}
    SOURCE -->|"User request in CLI"| TASK["do-task-solo"]

    ISSUEMODE -->|"solo"| SOLO["do-issue-solo"]
    ISSUEMODE -->|"guided"| GUIDED["do-issue-guided"]

    SOLO --> SD1["Solution Design"]
    SD1 --> IP1["Implementation Plan"]
    IP1 --> SCOPE1{">8 steps?"}
    SCOPE1 -->|"no"| EXEC1["Execute Plan"]
    SCOPE1 -->|"yes"| TB1["Task Breakdown"] --> EXEC1
    EXEC1 --> VERIFY1["Verify + Review"]
    VERIFY1 --> PR1["Create PR"]

    GUIDED --> SD2["Solution Design"]
    SD2 -->|"checkpoint"| IP2["Implementation Plan"]
    IP2 --> SCOPE2{">8 steps?"}
    SCOPE2 -->|"no"| EXEC2["Execute Plan"]
    SCOPE2 -->|"yes"| TB2["Task Breakdown"] -->|"checkpoint"| EXEC2
    EXEC2 --> VERIFY2["Verify + Review"]
    VERIFY2 -->|"checkpoint"| PR2["Create PR"]

    TASK --> SD3["Formalise Task → Solution Design"]
    SD3 --> IP3["Implementation Plan"]
    IP3 --> SCOPE3{">8 steps?"}
    SCOPE3 -->|"no"| EXEC3["Execute Plan"]
    SCOPE3 -->|"yes"| TB3["Task Breakdown"] --> EXEC3
    EXEC3 --> VERIFY3["Verify + Review"]
    VERIFY3 --> PR3["Create PR"]

    style SOLO fill:#e6f3ff
    style GUIDED fill:#fff3e6
    style TASK fill:#e6ffe6
```

| Workflow            | Human involvement                                     | Use case                                                                      |
| ------------------- | ----------------------------------------------------- | ----------------------------------------------------------------------------- |
| **do-issue-solo**   | None until PR review                                  | Unattended development - LLM works autonomously from a GitHub issue           |
| **do-issue-guided** | Checkpoints at design, plan, review, and completion   | Supervised development - human validates approach at key decision points      |
| **do-task-solo**    | Initial request only, then none until PR review       | Local autonomous development - user describes the task in the CLI, no GitHub issue required |

All three workflows follow the same phases: solution design → implementation plan → (optional task breakdown) → execution → verification → PR creation. When a plan exceeds 8 steps, the `task-breakdown` skill decomposes it into independently trackable sub-tasks with dependency ordering, which are then executed in sequence. The differences between workflows are where work originates and where human checkpoints occur.

**do-task-solo** stores all artifacts locally under `.maverick/do-tasks/<TASK-ID>/` (task description, design, plan, completion) instead of GitHub issue comments. Task documents are committed to version control; only the state file is gitignored.

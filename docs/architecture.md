---
title: Maverick Architecture
scope: Best practice workflows
relates-to:
last-verified: 2026-03-02
---

# Architecture

## Skills

Skills are markdown files with YAML frontmatter that load into the LLM's context window. They provide machine-readable guidance - dense, factual, and actionable.

| Category            | Skills                                                                             | Purpose                                                        |
| ------------------- | ---------------------------------------------------------------------------------- | -------------------------------------------------------------- |
| **Best Practices**  | logging, alerting, linting, unit-testing, cicd                                     | Define standards for each practice area                        |
| **Workflow**        | do-issue-solo, do-issue-guided, create-solution-design, create-implementation-plan | Orchestrate multi-step development workflows                   |
| **Execution**       | plan-execution, local-verification, subagents                                      | Control how plans are executed and verified                    |
| **Git & GitHub**    | git-workflow, github-issue-workflow                                                | Define branching, commit, and issue interaction patterns       |
| **CI/CD Platforms** | cicd-github, cicd-gitlab, cicd-azure                                               | Platform-specific pipeline monitoring                          |
| **Governance**      | scope-boundaries, claude-code-recovery, systematic-debugging                       | Define hard limits and resilience patterns                     |
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

Maverick provides two primary workflows for working on GitHub issues:

```mermaid
flowchart TD
    ISSUE["GitHub Issue"] --> MODE{"Workflow mode?"}

    MODE -->|"solo"| SOLO["do-issue-solo"]
    MODE -->|"guided"| GUIDED["do-issue-guided"]

    SOLO --> SD1["Solution Design"]
    SD1 --> IP1["Implementation Plan"]
    IP1 --> EXEC1["Execute Plan"]
    EXEC1 --> VERIFY1["Verify + Review"]
    VERIFY1 --> PR1["Create PR"]

    GUIDED --> SD2["Solution Design"]
    SD2 -->|"human approval"| IP2["Implementation Plan"]
    IP2 -->|"human approval"| EXEC2["Execute Plan"]
    EXEC2 --> VERIFY2["Verify + Review"]
    VERIFY2 --> PR2["Create PR"]

    style SOLO fill:#e6f3ff
    style GUIDED fill:#fff3e6
```

| Workflow            | Human involvement                        | Use case                                                                |
| ------------------- | ---------------------------------------- | ----------------------------------------------------------------------- |
| **do-issue-solo**   | None until PR review                     | Unattended development - LLM works autonomously end-to-end              |
| **do-issue-guided** | Approval gates at design and plan phases | Supervised development - human validates approach before implementation |

Both workflows follow the same phases: solution design → implementation plan → execution → verification → PR creation. The difference is where human checkpoints occur.

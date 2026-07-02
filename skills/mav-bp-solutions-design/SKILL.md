---
name: mav-bp-solutions-design
description: Solutions design conventions for all projects. Covers the requirement for design before implementation, design documentation persistence, requirements traceability, and Architecture Decision Records. Applied before starting implementation of any non-trivial change.
---

# Solutions Design Standards

Ensure every non-trivial change is designed before it is implemented. Design prevents wasted effort, surfaces risks early, and creates a durable record of decisions for future developers.

## Principles

1. **Design before code** — implementation begins only after a design exists and is validated. The cheapest time to find a flaw is before any code is written.
2. **Based on requirements** — every design traces back to a requirement, user story, or task. Design without requirements is speculation.
3. **Assessed against the existing codebase** — design considers current architecture, patterns, conventions, and dependencies. It does not operate in a vacuum.
4. **Identify affected areas** — the design explicitly lists which code, services, data stores, APIs, and configurations will change.
5. **Validated against requirements** — the design is checked to confirm it addresses every acceptance criterion before implementation starts.
6. **Documented and persisted** — designs are saved as durable artifacts so future developers can understand why decisions were made, not just what code exists.

## Design is Mandatory Before Implementation

Every change — from a one-line bug fix to a multi-sprint feature — requires some level of design. The depth scales with the change's complexity and risk, but the act of thinking through the approach before coding is always required.

### Why

- Forces you to understand the problem before solving it
- Reveals gaps in requirements before they become gaps in code
- Identifies integration risks, data migration needs, and backwards compatibility concerns
- Creates a reviewable artifact that catches design-level mistakes before they become code-level mistakes
- Provides context for code reviewers who need to understand intent, not just diff

### The Minimum Bar

Even for the smallest change, the developer must be able to answer:
- What is the requirement or problem being solved?
- What will change in the codebase?
- How will I verify the change works?

If these questions cannot be answered clearly, more design work is needed.

## Design Must Be Based on Requirements

A design that does not trace back to a requirement is unanchored — it may solve the wrong problem, over-engineer a simple need, or miss the actual acceptance criteria.

### Rules

- **Every design references its source requirement** — GitHub issue, user story, task description, or bug report
- **Acceptance criteria drive the design** — the design must explain how each acceptance criterion will be satisfied
- **If requirements are ambiguous, clarify before designing** — do not guess. Ask the stakeholder, update the requirement, then design.
- **If requirements are missing, flag it** — a design cannot be complete if the requirements are incomplete. Document assumptions explicitly.

## Codebase Assessment

Before proposing a design, explore and understand the relevant parts of the existing codebase:

### What to Assess

| Area | Questions |
| ---- | --------- |
| **Architecture** | What is the high-level structure? Monolith, microservices, modular monolith? Where does the new change fit? |
| **Patterns in use** | What patterns does the codebase already use for similar functionality? (Repository pattern, service layer, event-driven, etc.) |
| **Dependencies** | What libraries, frameworks, and services are already in use? Can the design leverage existing dependencies rather than adding new ones? |
| **Data model** | What is the current data model? Does the design require schema changes, migrations, or new tables? |
| **API surface** | Does the change affect public APIs, internal APIs, or integration contracts? |
| **Test infrastructure** | What testing patterns exist? How will the design be tested using existing infrastructure? |

### Rules

- **Follow existing patterns** — unless there is a documented, justified reason to introduce a new pattern, use what the codebase already uses
- **Do not introduce new dependencies without justification** — if the codebase uses library A for HTTP, do not add library B for the same purpose
- **Respect module boundaries** — understand where responsibilities live and do not scatter new logic across unrelated modules

## Affected Area Identification

The design must explicitly list what will change. This serves as both a planning tool and a review aid.

### What to Document

- **Files and modules** that will be created, modified, or deleted
- **Database changes** — new tables, columns, migrations, index changes
- **API changes** — new endpoints, modified request/response schemas, deprecations
- **Configuration changes** — new environment variables, feature flags, config files
- **External service interactions** — new integrations, changed API calls, updated contracts
- **UI changes** — new screens, modified components, changed user flows
- **Test changes** — new test files, modified test fixtures, updated mocks

### Why This Matters

- Enables accurate effort estimation
- Helps reviewers know what to look for
- Surfaces unintended coupling (if a "small" change touches 15 modules, the design may need rethinking)
- Provides a checklist for implementation completeness

## Requirements Validation

Before implementation begins, the design must be validated against the original requirements:

### Validation Checklist

1. **Every acceptance criterion is addressed** — the design explains how each criterion will be met
2. **No scope creep** — the design does not include work beyond what the requirements specify
3. **Edge cases considered** — error states, empty states, boundary conditions, concurrent access
4. **Non-functional requirements covered** — performance, security, accessibility, if specified
5. **Backwards compatibility assessed** — will existing users, clients, or integrations be affected?

## Design Persistence

Designs must be saved as durable artifacts. A design that exists only in a developer's head or a Slack conversation is not a design — it is a plan that will be lost.

### Persistence by Change Size

| Change size | Where to persist the design | Format |
| ----------- | --------------------------- | ------ |
| **Trivial** (bug fix, config change, copy update) | In the issue or PR description | 2-3 sentences: what, why, how |
| **Medium** (new feature, significant refactor, new integration) | `docs/designs/` directory or detailed issue/PR description | Structured design document with sections for context, approach, affected areas, and alternatives considered |
| **Large** (architectural change, new service, major migration, technology change) | Architecture Decision Record in `docs/decisions/` | Full ADR with context, decision, consequences, and alternatives |

### Architecture Decision Records (ADRs)

For significant architectural decisions, use the ADR format:

```
# ADR-NNN: Title of Decision

## Status
Proposed | Accepted | Deprecated | Superseded by ADR-XXX

## Context
What is the situation that requires a decision? What forces are at play?

## Decision
What is the decision that was made?

## Consequences
What are the positive and negative consequences of this decision?

## Alternatives Considered
What other options were evaluated and why were they rejected?
```

### ADR Rules

- **Number ADRs sequentially** — `ADR-001`, `ADR-002`, etc.
- **ADRs are immutable once accepted** — if a decision changes, create a new ADR that supersedes the old one
- **Store in version control** — ADRs live in `docs/decisions/` and follow the same review process as code
- **Reference from code** — when code implements an ADR decision, link to the ADR in a comment or README

### Design Documents

For medium-sized changes that do not warrant a full ADR:

- Store in `docs/designs/` with a descriptive filename (e.g., `user-export-feature.md`)
- Include at minimum: context, approach, affected areas, and how requirements are addressed
- Link from the implementing issue or PR
- Design documents may be updated as the implementation reveals new information

## Design Workflow Reference

For the step-by-step process of producing a solution design (codebase exploration, design structure, validation steps), use the `mav-create-solution-design` workflow skill. That skill implements the mechanics; this skill defines the standards that every design must meet.

## Design Scaling

Not every change needs a 10-page design document. The investment in design should be proportional to the risk and complexity of the change:

### Trivial Changes

**Examples**: fix a typo, update a dependency, change a log message, adjust a CSS value.

**Design effort**: Mental model only. Capture the "what and why" in the commit message or PR description.

**Artifact**: 2-3 sentences in the PR description.

### Medium Changes

**Examples**: add a new API endpoint, implement a feature behind a flag, refactor a module, add a new integration.

**Design effort**: 30-60 minutes exploring the codebase, writing a structured design.

**Artifact**: Structured design in the issue description, PR description, or a document in `docs/designs/`.

**Sections to include**:
- Problem statement and requirements reference
- Proposed approach
- Affected areas (files, APIs, database, config)
- Alternatives considered (at least one)
- How acceptance criteria will be verified

### Large Changes

**Examples**: introduce a new service, migrate a database, change the authentication system, adopt a new framework, restructure the module layout.

**Design effort**: Hours to days. May require multiple rounds of review.

**Artifact**: Full ADR in `docs/decisions/` and/or a detailed design document in `docs/designs/`.

**Sections to include**:
- Everything from medium, plus:
- Architecture diagrams (component, sequence, data flow)
- Data migration plan (if applicable)
- Rollback strategy
- Performance and scalability considerations
- Security implications
- Phased implementation plan

## Detecting Design Issues in Code Review

| Pattern | Issue | Fix |
| ------- | ----- | --- |
| PR with no design context in description | Missing design artifact | Add design rationale to PR description or link to design doc |
| Implementation does not match the design | Design-code drift | Update design or adjust implementation to match |
| Change touches many unrelated modules | Possible design gap | Review whether the change should be decomposed differently |
| New pattern introduced without justification | Convention violation | Follow existing patterns or create an ADR justifying the new approach |
| No acceptance criteria referenced | Requirements traceability gap | Link to the requirement and explain how each criterion is met |
| Architectural decision with no ADR | Decision will be lost | Write an ADR before or alongside the implementation |
| Design doc exists but is stale | Documentation rot | Update the design doc to reflect what was actually built |
| Requirements ambiguity resolved by guessing | Risk of building the wrong thing | Clarify with stakeholder before proceeding |

<!-- maverick-plugin-version: 3.3.9 -->

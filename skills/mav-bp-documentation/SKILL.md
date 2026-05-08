---
name: mav-bp-documentation
description: Documentation conventions for all projects. Covers minimum documentation requirements, documentation freshness enforcement, AI-readable structure, and the relationship between human and machine audiences. Applied when creating or reviewing project documentation.
---

# Documentation Standards

Ensure all projects have accurate, structured, and up-to-date documentation that serves both human developers and AI agents.

## Principles

1. **All projects must have documentation** — no project is too small for a README and basic architecture overview
2. **Human-readable but AI-optimised** — documentation is written for humans first, but structured so AI agents can parse and act on it reliably
3. **Kept up to date** — stale documentation is worse than no documentation; freshness is enforced via workflow
4. **Enforced via workflow** — documentation updates are part of the development process, not an afterthought
5. **Documentation as code** — docs live in the repository alongside the code they describe, versioned and reviewed together

## Minimum Documentation Requirements

Every project must have the following at a minimum:

| Document              | Location                          | Purpose                                                         |
| --------------------- | --------------------------------- | --------------------------------------------------------------- |
| README                | `README.md` (repo root)          | Project purpose, quick start, prerequisites, how to run/test    |
| Architecture overview | `docs/architecture.md` or equiv. | System components, data flow, key design decisions              |
| Setup guide           | README or `docs/setup.md`        | Step-by-step instructions to go from clone to running locally   |
| API docs              | `docs/api/` or inline            | Required if the project exposes an API (REST, GraphQL, CLI, SDK)|
| CLAUDE.md             | Repo root                        | AI agent instructions — see dedicated section below             |

### README Structure

A README should contain, in order:

1. **Project name and one-line description**
2. **Prerequisites** — runtime versions, system dependencies
3. **Quick start** — clone, install, run (copy-pasteable commands)
4. **Development** — how to run tests, lint, build
5. **Deployment** — how and where it deploys (or link to deployment docs)
6. **Contributing** — link to contributing guide or inline conventions

## Documentation Structure and Organisation

- Keep docs close to the code they describe — prefer `docs/` in the repo over external wikis
- Use flat structures for small projects; use subdirectories (`docs/api/`, `docs/guides/`, `docs/architecture/`) for larger ones
- Name files descriptively — `docs/database-migrations.md`, not `docs/db.md`
- Use consistent heading hierarchy — `#` for title, `##` for sections, `###` for subsections
- Include diagrams where they clarify — Mermaid syntax preferred for version-controlled diagrams

## Writing for Dual Audience

Documentation serves two audiences: human developers and AI agents. Optimise for both.

### Human-Readable

- Write in plain language, avoid unnecessary jargon
- Use examples liberally — show, don't just tell
- Explain the "why" alongside the "what"
- Keep paragraphs short and scannable

### AI-Agent-Optimised

- **Dense and precise** — avoid filler words and vague statements; every sentence should carry information
- **Structurally consistent** — use the same heading patterns, table formats, and section ordering across documents
- **Machine-parseable** — use tables, lists, and code blocks rather than prose for structured data
- **Explicit over implicit** — state assumptions, constraints, and boundaries directly rather than relying on context
- **Self-contained sections** — each section should be understandable without reading the entire document

## Documentation Freshness

Stale documentation actively harms a project. Freshness is enforced, not hoped for.

### Rules

- **Code changes require doc updates** — if a PR changes behaviour, public APIs, configuration, or setup steps, the corresponding documentation must be updated in the same PR
- **Broken docs are bugs** — treat outdated documentation with the same urgency as broken tests
- **Review docs in code review** — reviewers must check that documentation matches the change

### Enforcement

- Pre-commit hooks or CI checks can flag PRs that modify source files without touching relevant docs
- Workflow skills (do-tech-docs, do-docs) enforce documentation creation and updates as part of the development process
- The code-review agent checks for documentation coverage

## CLAUDE.md and Project-Level AI Instructions

Every project should have a `CLAUDE.md` at the repository root. This file provides context and instructions to AI agents working on the codebase.

### What to Include

- **Project overview** — what the project does, its architecture at a glance
- **Build and run commands** — exact commands to install, build, test, lint, deploy
- **Key conventions** — naming, file structure, patterns the project follows
- **What to avoid** — anti-patterns, deprecated approaches, files not to touch
- **Architecture notes** — how components relate, data flow, key abstractions

### What NOT to Include

- Secrets, credentials, or environment-specific values
- Information that changes every sprint — keep it stable
- Duplicates of what is already in README or other docs — link instead

## What NOT to Document

- **Implementation details that change frequently** — internal algorithms, private function behaviour, temporary workarounds. These go stale immediately.
- **Auto-generated content** — API docs generated from OpenAPI specs, type docs generated from code. Commit the generator config, not the output.
- **Obvious code** — well-named functions and types are self-documenting. Don't write docs that restate what the code already says.
- **Aspirational features** — don't document what the system might do someday. Document what it does now.

## Documentation Review in Code Review

When reviewing a PR, check documentation alongside code:

| Check                                              | Action                                                       |
| -------------------------------------------------- | ------------------------------------------------------------ |
| PR changes a public API                            | Verify API docs are updated                                  |
| PR changes setup/install steps                     | Verify README or setup guide is updated                      |
| PR adds a new component or service                 | Verify architecture docs are updated                         |
| PR changes configuration or environment variables  | Verify relevant docs reflect the change                      |
| PR introduces a new pattern or convention          | Verify CLAUDE.md or contributing guide is updated            |
| PR deletes or renames a feature                    | Verify old documentation references are removed or updated   |

## Detailed Documentation Workflows

For creating or updating documentation, use the dedicated documentation skills:

- **do-tech-docs** — technical documentation standards covering document structure, writing style, file organisation, Mermaid diagrams, and validation
- **do-docs** — workflow for creating, restructuring, or updating technical documentation

## Detecting Documentation Issues

When reviewing code or auditing a project, flag these patterns:

| Pattern                                          | Issue                        | Fix                                                      |
| ------------------------------------------------ | ---------------------------- | -------------------------------------------------------- |
| No README.md in repo root                        | Missing essential docs       | Create README with minimum required sections             |
| README has no setup/run instructions             | Unusable for new developers  | Add quick-start commands                                 |
| Code change without doc update                   | Documentation drift          | Update relevant docs in the same PR                      |
| No CLAUDE.md                                     | AI agents lack context       | Create CLAUDE.md with project overview and commands      |
| Docs reference deleted features or old APIs      | Stale documentation          | Remove or update stale references                        |
| Architecture docs missing for multi-service project | Unclear system design     | Create architecture overview with component diagram      |
| Inline comments restating obvious code           | Noise, not documentation     | Remove; write higher-level docs instead                  |
| Documentation in external wiki only              | Not versioned with code      | Move to repo `docs/` directory                           |

<!-- maverick-plugin-version: 3.1.1-dev -->

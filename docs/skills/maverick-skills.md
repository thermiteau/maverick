# Maverick Skills

This page lists every skill shipped with the Maverick plugin, generated from the source skill configs in `src/maverick/skills/`.


## do-adopt

Scan a project for missing best-practice areas and implement the top recommendation for each gap. Currently covers linting and unit testing. Installs tools, writes configs, and adds CI steps.


## do-cybersecurity-review

Run a security audit of the project's existing codebase and write a findings report to docs/security-audit.md. Covers secrets exposure, dependency vulnerabilities, authentication and authorisation patterns, input validation, transport security, and common OWASP risks. Run as part of do-init or on demand.


## do-docs

Create, restructure, or update technical documentation. Handles greenfield projects, refactoring non-compliant docs, and incremental updates after code changes.


## do-epic

Work on a multi-story GitHub epic end-to-end. Builds a DAG from the child stories, groups them into waves, runs waves in parallel via per-story worktrees, ejects PRs that fail agent-code-review for human handling, and propagates blocks to downstream stories. Requires git worktrees.


## do-init

Initialise a project for use with Maverick — verifies the GitHub App, installs the CLI if needed, writes the project config with integration tracking, scaffolds docs, generates project skills, scaffolds the mandatory remote code-review workflow, runs an initial cybersecurity audit, then commits the changes and opens a PR.


## do-install

Install the maverick CLI tool system-wide from the plugin directory.


## do-issue-guided

Work on a GitHub issue interactively with the user. Proceeds autonomously through routine work but pauses for confirmation at key decision points and when uncertain.


## do-issue-solo

Work on a GitHub issue end-to-end autonomously, only pausing when blocked or when clarification is needed.


## do-maverick-alignment

Analyze a project's codebase against Maverick standard practices and write a findings report. Checks linting, unit tests, integration tests, documentation, CI/CD, security, dependency management, observability, source control, and more. Run when onboarding an existing project or on demand.


## do-pullrequest-review

How to process code review feedback — verify before implementing, push back when wrong, clarify before acting on partial understanding. Applied when receiving review from the code-reviewer agent or human reviewers.


## do-recommend

Scan a project for missing best-practice areas and recommend 1-3 technology options for each gap. Currently covers linting and unit testing. Writes recommendations to docs/maverick/recommendations/<topic>.md.


## do-tech-docs

Technical documentation standards — document structure, writing style, file organisation, mermaid diagrams, and validation. Referenced by do-docs and tech-docs-writer.


## do-upskill

Use when a best-practice skill needs project-specific implementation details and no project skill exists at docs/maverick/skills/<topic>/SKILL.md. Scans the codebase and generates a project-specific skill file.


## mav-block-propagation

Idempotent, resumable propagation of a `blocked-by:#N` block from an ejected story to every transitive downstream story in the epic DAG. Triggered when agent-code-reviewer ejects a PR for human handling.


## mav-bp-accessibility

Accessibility conventions for projects with user-facing interfaces. Covers WCAG 2.1 AA compliance, semantic HTML, keyboard navigation, colour contrast, screen reader support, and automated a11y testing. Applied when building or reviewing user-facing web or mobile applications.


## mav-bp-alerting

Alerting conventions for fatal errors in applications. Covers severity levels, alert context, centralised notification, and project alerting guidance. Applied when writing error handling or reviewing code.


## mav-bp-api-design

API design conventions for projects with API surfaces. Covers REST and GraphQL standards, versioning, error formats, pagination, documentation as code, and backwards compatibility. Applied when designing, implementing, or reviewing APIs.


## mav-bp-application-security

Application security conventions for all projects. Covers OWASP Top 10 awareness, input validation, secrets management, dependency scanning, SAST/DAST integration, and security headers. Applied when writing or reviewing any code.


## mav-bp-cicd

Platform-agnostic CI/CD conventions. Covers pipeline stages, quality gates, environment promotion, secrets management, artifact handling, and deployment boundaries. Applied when configuring or reviewing CI/CD pipelines.


## mav-bp-cicd-azure

Monitoring Azure DevOps pipelines after pushing. Covers checking pipeline status, diagnosing build/release failures, and respecting pipeline boundaries. Used as a dependency from workflow skills.


## mav-bp-cicd-bitbucket

Monitoring Bitbucket Pipelines after pushing. Covers checking pipeline status, diagnosing build failures, and respecting pipeline boundaries. Used as a dependency from workflow skills.


## mav-bp-cicd-github

Monitoring GitHub Actions pipelines after pushing. Covers checking workflow status, diagnosing CI failures, and respecting pipeline boundaries. Used as a dependency from workflow skills.


## mav-bp-cicd-gitlab

Monitoring GitLab CI/CD pipelines after pushing. Covers checking pipeline status, diagnosing job failures, and respecting pipeline boundaries. Used as a dependency from workflow skills.


## mav-bp-code-review

Code review conventions for all projects. Covers mandatory review requirements, review scope, PR sizing, reviewer and author responsibilities, and automated review integration. Applied when creating or reviewing pull requests.


## mav-bp-database-management

Database and data management conventions for all projects using databases. Covers schema migrations, backup strategy, data lifecycle, index management, and connection pooling. Applied when designing, implementing, or reviewing database interactions.


## mav-bp-dependency-management

Dependency management conventions for all projects. Covers lock files, version pinning, vulnerability scanning, license compliance, update strategy, and minimal dependency principle. Applied when adding, updating, or reviewing dependencies.


## mav-bp-documentation

Documentation conventions for all projects. Covers minimum documentation requirements, documentation freshness enforcement, AI-readable structure, and the relationship between human and machine audiences. Applied when creating or reviewing project documentation.


## mav-bp-environment-management

Environment management conventions for all projects. Covers reproducible local development, environment parity, .env patterns, developer onboarding, and containerised development. Applied when setting up or reviewing development environments.


## mav-bp-error-handling

Error handling conventions for all applications. Covers error propagation, retry strategies, circuit breakers, graceful degradation, error boundaries, and typed errors. Applied when writing or reviewing error handling code.


## mav-bp-infrastructure-as-code

Infrastructure as Code conventions for all deployed projects. Covers IaC principles, environment parity, secrets management in IaC, version control, and runbook fallback for unsupported platforms. Applied when reviewing or configuring infrastructure.


## mav-bp-integration-testing

Integration testing conventions for applications. Covers test scope, external dependency management, environment setup, data isolation, and project testing guidance. Applied when writing or reviewing integration tests.


## mav-bp-linting

Linting conventions for applications. Covers linter selection, rule configuration, auto-formatting, CI integration, and project linting guidance. Applied when writing or reviewing code, or configuring developer tooling.


## mav-bp-logging

Logging conventions for backend and frontend applications. Covers log levels, structured logging, centralised aggregation, and project logging guidance. Applied when writing or reviewing code that includes logging.


## mav-bp-observability

Observability conventions for deployed applications. Covers metrics collection, distributed tracing, health checks, SLIs/SLOs, and dashboards. Complements the logging and alerting skills to complete the observability picture. Applied when designing or reviewing operational aspects of services.


## mav-bp-remote-code-review

Mandatory remote code review on every pull request. Defines the contract for a GitHub Actions workflow that runs the agent-code-reviewer in CI when a PR is opened, synchronized, or reopened. Used as a dependency by do-issue-solo and do-epic to enforce the review gate, and by do-maverick-alignment to audit the workflow's presence.


## mav-bp-solutions-design

Solutions design conventions for all projects. Covers the requirement for design before implementation, design documentation persistence, requirements traceability, and Architecture Decision Records. Applied before starting implementation of any non-trivial change.


## mav-bp-source-control

Source control conventions for all projects. Covers the requirement for remote repositories, repository hygiene, .gitignore standards, and sensitive file protection. Applied as a foundational requirement for all projects.


## mav-bp-task-tracking

Task tracking and management conventions for all projects. Covers the requirement for external task tracking, issue hygiene, workflow integration, and traceability between tasks and code changes. Applied as a foundational project management requirement.


## mav-bp-unit-testing

Unit testing conventions for applications. Covers test design, isolation, structure, mocking discipline, and project testing guidance. Applied when writing or reviewing unit tests.


## mav-bp-versioning

Versioning and deprecation conventions for projects producing libraries, APIs, or SDKs. Covers semantic versioning, changelog maintenance, deprecation policies, and breaking change management. Applied when releasing or reviewing versioned artifacts.


## mav-claude-code-recovery

Patterns for Claude Code workflow resilience — state persistence, crash recovery, command failure handling, subagent failure handling, and artefact durability. Not about application-level error handling.


## mav-create-solution-design

How to produce a solution design for a GitHub issue or task. Covers codebase exploration, design structure, and validation. Used as a dependency from workflow skills.


## mav-create-tasks

How to decompose a solution design into discrete, independently implementable tasks. Used as a dependency from workflow skills.


## mav-durability-on-gh

Durability conventions for multi-instance Maverick workflows. Covers cold-start hydration from GitHub, marker-write protocols, push-per-task cadence, and recreating worktrees from remote branches. GitHub is the source of truth; local files are a cache.


## mav-git-workflow

Git branching strategy, commit conventions, merge conflict handling, and branch lifecycle. Implements a simplified Gitflow with protected branches and conventional commits. Covers worktree-based multi-story workflows and cross-references stacked-PR handling.


## mav-github-issue-workflow

Standard patterns for interacting with GitHub issues — reading, commenting, updating, state tracking, branching, and PR creation. Use as a dependency from workflow skills, not directly.


## mav-local-verification

Pre-push code quality verification — lint, typecheck, and tests run locally before pushing. Covers discovering project verification commands, run order, scope-appropriate checks, and fixing failures. Used as a dependency from workflow skills.


## mav-multi-instance-coordination

Claim, lease, heartbeat, and release protocols for when multiple Claude Code instances may act on the same issue or epic concurrently. GitHub labels and marker comments are the coordination surface; local state is a cache.


## mav-plan-execution

How to execute an implementation plan step-by-step. Covers the execution loop, verification discipline, failure handling, progress tracking, crash recovery, and acceptance criteria. Adapts behaviour based on whether the caller is solo (autonomous) or guided (human checkpoints). Used as a dependency from workflow skills.


## mav-scope-boundaries

Defines what Claude Code must refuse to do without explicit authorisation. Covers infrastructure, auth, destructive git, and production systems. Applied automatically to all workflows.


## mav-stacked-prs

How to stack a PR on top of an unmerged sibling branch, and how to retarget it to the repo's default branch once the sibling merges. Prevents orphan-merge incidents when a dependent story is ready before its parent.


## mav-systematic-debugging

Use when encountering any bug, test failure, or unexpected behaviour during implementation. Requires root cause investigation before proposing fixes.


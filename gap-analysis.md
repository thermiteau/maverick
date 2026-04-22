# Maverick Best Practice Gap Analysis

**Date:** 2026-03-30
**Purpose:** Compare user expectations against current Maverick skill coverage. Identify gaps, partial coverage, and areas needing new or updated skills.

---

## Summary

| # | Expected Best Practice | Current Status | Verdict |
|---|------------------------|---------------|---------|
| 1 | Alerting | `mav-bp-alerting` exists | **Covered** |
| 2 | CI/CD | `mav-bp-cicd` + 3 vendor skills exist | **Covered** |
| 3 | Linting | `mav-bp-linting` exists | **Covered** |
| 4 | Source Control | `mav-git-workflow` exists | **Partial Gap** |
| 5 | Documentation | `do-tech-docs` exists | **Partial Gap** |
| 6 | Infrastructure as Code | No skill exists | **Full Gap** |
| 7 | Unit Testing | `mav-bp-unit-testing` exists | **Partial Gap** |
| 8 | Integration Testing | `mav-bp-integration-testing` exists | **Partial Gap** |
| 9 | Solutions Design | `mav-create-solution-design` exists | **Partial Gap** |
| 10 | Task Tracking & Management | `mav-create-tasks` + `mav-github-issue-workflow` exist | **Partial Gap** |
| 11 | Application Security | No skill exists | **Full Gap** |
| 12 | Dependency Management | No skill exists | **Full Gap** |
| 13 | Observability / Monitoring | `mav-bp-logging` + `mav-bp-alerting` cover parts | **Partial Gap** |
| 14 | API Design Standards | No skill exists | **Full Gap** |
| 15 | Database & Data Management | No skill exists | **Full Gap** |
| 16 | Code Review | `agent-code-reviewer` exists but no BP skill | **Partial Gap** |
| 17 | Error Handling | No skill exists | **Full Gap** |
| 18 | Accessibility (a11y) | No skill exists | **Full Gap** |
| 19 | Environment Management | No skill exists | **Full Gap** |
| 20 | Versioning & Deprecation | No skill exists | **Full Gap** |

---

## Detailed Analysis

### 1. Alerting — **Covered**

**Expectation:** Projects deployed to remote servers/IaaS/PaaS/devices should have alerting so business/product owners know when errors occur.

**Current state:** `mav-bp-alerting` covers this well:
- Three severity levels (critical, high, warning) with expected response times
- Required alert context fields for immediate investigation
- Deduplication to prevent alert fatigue
- Separation of alerting from logging concerns
- Vendor-agnostic principles

**Gaps:** None significant. The skill is vendor-agnostic and comprehensive.

---

### 2. CI/CD — **Covered**

**Expectation:** All projects should have CI/CD using industry products (GitHub Workflows, Bitbucket Pipelines, CircleCI, etc.).

**Current state:** Strong coverage:
- `mav-bp-cicd` — platform-agnostic standards (pipeline stages, quality gates, environment promotion, secrets management)
- `mav-bp-cicd-github` — GitHub Actions specifics
- `mav-bp-cicd-gitlab` — GitLab CI/CD specifics
- `mav-bp-cicd-azure` — Azure DevOps specifics

**Gaps:**
- **Missing vendor skills:** No Bitbucket Pipelines, CircleCI, or Jenkins vendor skill. The core `mav-bp-cicd` covers principles, but there are no platform-specific monitoring/troubleshooting guides for these platforms.
- **Minor:** Consider whether additional vendor skills are needed or if the agnostic skill is sufficient for unlisted platforms.

---

### 3. Linting — **Covered**

**Expectation:** Code should always have linting tools in place.

**Current state:** `mav-bp-linting` is comprehensive:
- Language-specific linter recommendations
- Pre-commit hooks for formatting
- CI lint gates
- Zero-error policy (no warnings)

**Gaps:** None significant.

---

### 4. Source Control — **Partial Gap**

**Expectation:**
- All projects must have source control
- Must have **remote** source control (GitHub, Bitbucket, etc.)
- Local-only git is a **hard fail**

**Current state:** `mav-git-workflow` covers branching strategy, commit conventions, and PR workflows well. It implicitly assumes remote hosting (references PRs, protected branches, etc.).

**Gaps:**
1. **No explicit remote-repository requirement.** The skill never states that a remote must exist or that local-only git is unacceptable. This is a stated hard-fail condition that should be explicitly enforced.
2. **No validation/check step.** There is no guidance for Claude to verify that a remote is configured (e.g., `git remote -v` check) before proceeding with work.
3. **Vendor-agnostic framing.** The skill is heavily Git-specific. While Git dominates, the expectation says "source control" broadly. The skill name and content are Git-only. This is likely fine in practice but worth noting.
4. **No mention of Bitbucket** as a remote host — only GitHub-specific issue/PR workflows exist (`mav-github-issue-workflow`). No equivalent for Bitbucket, GitLab (issues), or Azure Repos.

---

### 5. Documentation — **Partial Gap**

**Expectation:**
- Comprehensive documentation that is human-readable but designed for AI agents
- Must be kept up to date
- Preferably enforced via workflow (Claude Hook or git hook) to update docs after changes

**Current state:** `do-tech-docs` and the `tech-docs-writer` agent exist. They cover:
- Document structure, YAML frontmatter, Mermaid diagrams
- AI-first writing style (dense, precise, structurally consistent)
- File organisation conventions

**Gaps:**
1. **No enforced freshness mechanism.** The expectation explicitly calls for hooks or automated workflows to keep docs up to date. No such hook or automated trigger exists in Maverick. Documentation updates are manual — someone must invoke `do-docs` or the tech-docs-writer agent. There is no Claude Hook or git hook that automatically prompts for doc updates after code changes.
2. **No best-practice skill for documentation.** `do-tech-docs` is a workflow skill, not a best-practice skill. There is no `mav-bp-documentation` that establishes the universal principle that all projects must have documentation, what minimum documentation looks like, or how freshness should be enforced. The workflow skill tells you *how* to write docs but doesn't establish the *requirement* that docs must exist.
3. **Human readability.** The current docs skill explicitly targets LLM comprehension first. The expectation says "human readable, but ultimately designed for AI agents." The current skill may under-serve human readability.

---

### 6. Infrastructure as Code — **Full Gap**

**Expectation:**
- Some kind of IaC solution should be in place (simple VPS build/config to complex AWS/Azure deployments)
- If IaC is not possible for the target platform, document the gap and create runbook documentation for manual steps

**Current state:** **No skill exists for Infrastructure as Code.** The `mav-scope-boundaries` skill explicitly prevents Claude from making infrastructure changes without authorization, but there is no best-practice skill that establishes *what good IaC looks like* or *that IaC should exist*.

The CLI has AWS-specific commands (`build-ami`, `instance`, `infra`) but these are Maverick's own infrastructure tooling, not a best-practice guidance skill for user projects.

**What's needed:**
- A new `mav-bp-infrastructure-as-code` skill covering:
  - Principle: all infrastructure should be reproducible from code/config
  - Common IaC tools by platform (Terraform, Pulumi, CloudFormation, ARM/Bicep, Ansible, Docker Compose, etc.)
  - Version control for IaC alongside application code
  - Environment parity (dev/staging/prod from same templates)
  - Secrets management in IaC context
  - Fallback: when IaC is not possible, require runbook documentation with manual steps
  - Relationship to CI/CD (IaC changes should go through pipeline)

---

### 7. Unit Testing — **Partial Gap**

**Expectation:** All code should have unit tests with **at least 60% coverage**.

**Current state:** `mav-bp-unit-testing` is strong on testing principles:
- Behaviour-based testing, AAA structure, isolation, naming conventions
- Mocking discipline, test organisation

**Gaps:**
1. **No coverage threshold.** The skill explicitly avoids setting a coverage number: *"Coverage is a signal, not a goal — high coverage with weak assertions is worse than moderate coverage with strong assertions."* This directly contradicts the expectation of a 60% minimum. The philosophy is sound, but the expectation is a concrete 60% floor.
2. **No coverage enforcement guidance.** No mention of coverage tools, CI coverage gates, or how to configure/report coverage.

---

### 8. Integration Testing — **Partial Gap**

**Expectation:** All code should have integration tests with **at least 60% coverage**.

**Current state:** `mav-bp-integration-testing` covers:
- Test scope (cross-boundary interactions), data isolation, containerised dependencies
- What to test vs. what not to test

**Gaps:**
1. **No coverage threshold.** Same as unit testing — no concrete coverage number is established. The expectation requires 60%.
2. **No coverage measurement guidance.** Integration test coverage is harder to measure than unit test coverage. No guidance on how to measure or report it.
3. **Coverage for integration tests is non-standard.** The 60% expectation may need clarification — 60% of what? API endpoints? Service boundaries? Lines of code exercised during integration tests? This should be defined.

---

### 9. Solutions Design — **Partial Gap**

**Expectation:**
- Based on requirements
- Assessed and designed against existing codebase and documentation
- Identify affected areas if implemented
- Validated against requirements
- Clearly documented and saved

**Current state:** `mav-create-solution-design` covers most of this:
- Design structure includes: Approach, Areas Affected, Key Decisions, Risks/Open Questions, Acceptance Criteria Mapping
- Design validated against requirements before implementation
- Scaled to task size

**Gaps:**
1. **"Clearly documented and saved" is weak.** The current skill creates designs as GitHub issue comments or inline in the workflow. There is no guidance on persisting designs as durable artifacts (e.g., in a `docs/designs/` directory or ADR format). Once a GitHub issue is closed, the design is effectively buried.
2. **No best-practice skill wrapper.** Like documentation, this is a workflow skill (`mav-create-solution-design`), not a best-practice skill. There's no `mav-bp-solutions-design` that establishes the universal principle that designs must exist before implementation, regardless of workflow.
3. **No mention of requirements traceability.** The expectation says "based on requirements" — the skill handles this, but there's no explicit link back to formal requirements documents or acceptance criteria beyond what's in the issue.

---

### 10. Task Tracking & Management — **Partial Gap**

**Expectation:** Projects should use some kind of task tracking solution (Jira, GitHub Issues, etc.).

**Current state:**
- `mav-github-issue-workflow` — reading, commenting, updating GitHub issues
- `mav-create-tasks` — decomposing designs into tracked tasks (as issue comments or sub-issues)
- `do-issue-solo` / `do-issue-guided` — workflows driven by GitHub issues
- `do-task-solo` — workflow for tasks without GitHub issues (uses local task files)

**Gaps:**
1. **GitHub-only.** All task tracking integration is GitHub Issues specific. No support for Jira, Linear, Azure Boards, Trello, Asana, or other platforms.
2. **No best-practice skill.** There is no `mav-bp-task-tracking` that establishes the principle that all projects must use task tracking, regardless of platform. The current skills are workflow implementations, not principles.
3. **`do-task-solo` bypasses task tracking.** This workflow uses local task files instead of any external tracking system, which contradicts the expectation that an external system should be used.

---

### 11. Application Security — **Full Gap**

**Expectation:** All projects should have application security practices covering vulnerability prevention, detection, and remediation.

**Current state:** **No skill exists.** `mav-scope-boundaries` prevents Claude from making auth changes without review, but this is an operational guardrail, not a best-practice skill that guides developers on building secure software.

**What's needed — `mav-bp-application-security`:**
- OWASP Top 10 awareness and mitigation patterns
- Input validation and output encoding principles
- Authentication and authorisation design patterns
- Secrets management (no hardcoded credentials, vault usage, rotation)
- Security headers and CSP policies for web applications
- SAST/DAST integration into CI pipeline
- Secrets detection in commits (git-secrets, trufflehog, gitleaks)
- Dependency vulnerability scanning (covered more deeply by Dependency Management below, but referenced here)
- Secure defaults: HTTPS, parameterised queries, least privilege

**Priority:** **Critical** — the absence of security guidance is the single largest liability in the current skill set.

---

### 12. Dependency Management — **Full Gap**

**Expectation:** All projects should have a strategy for managing third-party dependencies safely and sustainably.

**Current state:** **No skill exists.** Linting and CI/CD skills don't cover dependency hygiene. No guidance on lock files, vulnerability scanning, license compliance, or update strategy.

**What's needed — `mav-bp-dependency-management`:**
- Lock files must be committed and reviewed (package-lock.json, uv.lock, Cargo.lock, etc.)
- Pin dependencies to exact versions or tight ranges — no floating `latest`
- Automated vulnerability scanning in CI (Dependabot, Snyk, Trivy, npm audit, pip-audit)
- License compliance checking — flag copyleft licenses (GPL) that may conflict with project licensing
- Update cadence strategy (automated PRs via Renovate/Dependabot, regular review cycle)
- Avoid abandoned/unmaintained packages — check last publish date, maintainer activity
- Minimal dependency principle — don't add a package for something trivially implementable
- Transitive dependency awareness — understand what your dependencies pull in

**Priority:** **Critical** — supply chain attacks are the #1 attack vector; unmanaged dependencies are the #1 source of known vulnerabilities in production.

---

### 13. Observability / Monitoring — **Partial Gap**

**Expectation:** Projects should have comprehensive observability covering metrics, tracing, and health monitoring — not just logging and alerting.

**Current state:** `mav-bp-logging` covers structured log output. `mav-bp-alerting` covers notification on fatal errors. Together these handle two of the "three pillars" partially, but the broader observability picture is missing.

**What's needed — `mav-bp-observability`:**
- Three pillars: logs (covered), metrics (missing), traces (missing)
- Metrics collection: application-level metrics (request rate, error rate, latency), business metrics, resource utilisation
- Distributed tracing: correlation IDs, span propagation, OpenTelemetry as the vendor-agnostic standard
- Health check endpoints: liveness, readiness, startup probes
- Dashboards: key service dashboards for operational visibility
- SLIs/SLOs: define what "healthy" means for each service, measure against it
- Relationship to existing skills: `mav-bp-logging` provides the log pillar, `mav-bp-alerting` provides the notification layer on top — this skill completes the picture

**Priority:** **High** — you're halfway there with logging + alerting; this closes the observability gap.

---

### 14. API Design Standards — **Full Gap**

**Expectation:** Projects with API surfaces should follow consistent, well-documented design standards.

**Current state:** **No skill exists.** No guidance on REST conventions, versioning, documentation, or contract testing.

**What's needed — `mav-bp-api-design`:**
- Consistent resource naming and URL structure (REST) or schema design (GraphQL)
- Versioning strategy (URL path, header, or query parameter — pick one and be consistent)
- Standard error response format (error code, message, details, correlation ID)
- Pagination patterns for list endpoints
- Rate limiting and throttling guidance
- API documentation as code (OpenAPI/Swagger, GraphQL schema introspection)
- Backwards compatibility contracts — breaking changes require version bump and deprecation period
- Input validation at the API boundary
- Idempotency for write operations where applicable

**Priority:** **High** — any project with an API surface (most projects) needs this.

---

### 15. Database & Data Management — **Full Gap**

**Expectation:** Projects using databases should have disciplined schema management, migration strategy, and data lifecycle practices.

**Current state:** **No skill exists.** Integration testing skill mentions containerised databases for testing but nothing about managing database schemas, migrations, or data lifecycle in production.

**What's needed — `mav-bp-database-management`:**
- Schema migrations must be versioned and reproducible (Flyway, Alembic, Knex, Prisma Migrate, Django migrations, etc.)
- Migrations are forward-only in production — never edit a deployed migration
- Every migration must be reversible (include rollback/down script)
- Backup and restore strategy documented and tested
- Data retention and archival policies
- Index strategy — don't add indexes speculatively, but ensure queries hitting production have appropriate indexes
- Seed data for development/testing — separate from production data
- No manual schema changes in any environment — all changes via migration tooling
- Connection pooling and resource management

**Priority:** **High** — unmigrated schema changes are a top cause of production incidents and deployment failures.

---

### 16. Code Review — **Partial Gap**

**Expectation:** All code changes should undergo review before merging to protected branches.

**Current state:** The `agent-code-reviewer` agent performs two-stage automated review (spec compliance + code quality). `mav-git-workflow` references PRs. But there is no best-practice skill establishing code review as a *mandatory practice* with defined standards.

**What's needed — `mav-bp-code-review`:**
- All changes to protected branches require at least one review before merge
- Review scope: correctness, security, maintainability, test coverage, documentation impact
- Reviewer responsibilities: understand the change, check edge cases, verify test coverage
- Author responsibilities: small PRs, clear descriptions, self-review before requesting review
- PR size guidance — prefer small, focused PRs; large PRs get worse reviews
- Review SLA — don't block teammates; reviews within one business day
- Automated review (linting, type checking, AI review) supplements but does not replace human review
- Relationship to existing agent: `agent-code-reviewer` handles automated review; this skill establishes the human + automated review requirement

**Priority:** **Medium** — the code-reviewer agent provides partial coverage; this formalises the practice.

---

### 17. Error Handling — **Full Gap**

**Expectation:** Code should handle errors consistently and gracefully, with clear patterns for failure modes.

**Current state:** **No skill exists.** `mav-bp-alerting` covers notifying humans about errors. `mav-bp-logging` covers recording errors. Neither covers how code should *handle* errors in the first place.

**What's needed — `mav-bp-error-handling`:**
- Fail fast on unrecoverable errors — don't swallow exceptions silently
- Use typed/structured errors, not generic strings
- Handle errors at the appropriate level — catch where you can act, propagate where you can't
- Retry with exponential backoff for transient failures (network, rate limits)
- Circuit breaker pattern for external service calls — stop hammering a failing dependency
- Graceful degradation — degrade feature, don't crash the application
- Error boundaries in frontend applications (React error boundaries, Vue error handlers)
- Never expose internal error details to end users (stack traces, SQL errors, file paths)
- Distinguish between client errors (4xx — caller's fault) and server errors (5xx — our fault)
- Relationship to logging/alerting: handle the error first, then log it, then alert if critical

**Priority:** **Medium** — foundational to code quality; directly impacts reliability and user experience.

---

### 18. Accessibility (a11y) — **Full Gap**

**Expectation:** User-facing applications should meet accessibility standards.

**Current state:** **No skill exists.** No guidance on WCAG compliance, semantic HTML, ARIA, or inclusive design.

**What's needed — `mav-bp-accessibility`:**
- WCAG 2.1 AA as the baseline standard for all user-facing web applications
- Semantic HTML first — use native elements before reaching for ARIA
- Keyboard navigation: all interactive elements reachable and operable via keyboard
- Colour contrast: minimum 4.5:1 for normal text, 3:1 for large text
- Alt text for images, labels for form inputs, captions for media
- Screen reader testing as part of QA
- Focus management for dynamic content (modals, SPAs, route changes)
- Automated accessibility testing in CI (axe-core, Lighthouse, pa11y)
- Scope: applies to web and mobile applications with user-facing UI; not applicable to CLIs, APIs, or backend services

**Priority:** **Medium** — increasingly a legal requirement (ADA, EAA); applicable to any project with a user-facing UI.

---

### 19. Environment Management — **Full Gap**

**Expectation:** Projects should have reproducible, well-documented development environments and clear environment parity across dev/staging/prod.

**Current state:** **No skill exists.** CI/CD skill covers pipeline environments. IaC (once created) would cover production infrastructure. But nothing covers local development setup or environment parity.

**What's needed — `mav-bp-environment-management`:**
- Local dev environment reproducible from repo checkout (devcontainers, Docker Compose, Nix, Vagrant)
- New developer to running application in under 30 minutes
- `.env.example` committed with all required variables (no values); `.env` in `.gitignore`
- Environment parity: dev, staging, and production use the same service versions and configurations where possible
- Environment-specific config via environment variables, not code branches or conditional logic
- Container-based local development for projects with external dependencies (databases, caches, queues)
- README or `CONTRIBUTING.md` with setup instructions (complements IaC and Documentation skills)
- Relationship to IaC: IaC manages deployed environments; this skill manages local/dev environments

**Priority:** **Medium** — directly impacts developer onboarding speed and "works on my machine" incidents.

---

### 20. Versioning & Deprecation — **Full Gap**

**Expectation:** Projects producing libraries, APIs, or SDKs should follow versioning standards and deprecation policies.

**Current state:** **No skill exists.** `mav-git-workflow` references tags on `main` but doesn't cover semantic versioning principles, changelog maintenance, or deprecation strategy.

**What's needed — `mav-bp-versioning`:**
- Semantic Versioning (SemVer) for libraries, packages, and APIs: MAJOR.MINOR.PATCH
- Breaking changes require major version bump — no exceptions
- Changelog maintained per release (CHANGELOG.md or GitHub Releases) — automated where possible (conventional-changelog, release-please)
- Deprecation policy: deprecated features marked in code, documented in changelog, removed only in next major version
- Pre-release versions for testing (alpha, beta, rc)
- Scope: primarily for projects that have consumers (libraries, APIs, SDKs, shared packages). Internal applications may use simplified versioning.
- Relationship to API Design: API versioning strategy is a subset of this practice

**Priority:** **Low** — critical for libraries/SDKs, less urgent for internal applications.

---

## Priority Actions

### Critical Priority (Security & Supply Chain)

| # | Action | Type | Notes |
|---|--------|------|-------|
| 1 | Create `mav-bp-application-security` | New skill | OWASP Top 10, input validation, secrets management, SAST/DAST in CI, security headers. Biggest single liability. |
| 2 | Create `mav-bp-dependency-management` | New skill | Lock files, vulnerability scanning, license compliance, update strategy, minimal dependency principle. |

### High Priority (Full Gaps — Core Engineering Practices)

| # | Action | Type | Notes |
|---|--------|------|-------|
| 3 | Create `mav-bp-infrastructure-as-code` | New skill | IaC principles, tool-agnostic guidance, runbook fallback for unsupported platforms. |
| 4 | Create `mav-bp-observability` | New skill | Metrics, distributed tracing, health checks, SLIs/SLOs. Completes the picture alongside existing logging + alerting skills. |
| 5 | Create `mav-bp-api-design` | New skill | REST/GraphQL conventions, versioning, error formats, pagination, OpenAPI docs, backwards compatibility. |
| 6 | Create `mav-bp-database-management` | New skill | Schema migrations, backup/restore, data retention, index strategy, connection pooling. |
| 7 | Create `mav-bp-error-handling` | New skill | Retry/backoff, circuit breakers, graceful degradation, error boundaries, typed errors. Foundational to reliability. |

### Medium Priority (Partial Gaps & Formalising Existing Practices)

| # | Action | Type | Notes |
|---|--------|------|-------|
| 8 | Create `mav-bp-documentation` | New skill | Establish docs-must-exist requirement, minimum standards, freshness enforcement. Separate from `do-tech-docs` workflow. |
| 9 | Create `mav-bp-source-control` | New skill | Remote-repo hard requirement, validation checks. Wraps `mav-git-workflow` with broader principles. |
| 10 | Create `mav-bp-task-tracking` | New skill | External task tracking is required. Vendor-agnostic principles. |
| 11 | Add coverage thresholds to `mav-bp-unit-testing` | Skill update | Add 60% minimum coverage floor, coverage tooling guidance, CI gate configuration. |
| 12 | Add coverage thresholds to `mav-bp-integration-testing` | Skill update | Add 60% minimum coverage floor (define what "coverage" means for integration tests), measurement guidance. |
| 13 | Create doc-freshness hook or workflow trigger | New hook/workflow | Automated mechanism to prompt doc updates after code changes. |
| 14 | Create `mav-bp-code-review` | New skill | Mandatory review before merge, review scope, PR size guidance, review SLA. Formalises what `agent-code-reviewer` partially covers. |
| 15 | Create `mav-bp-accessibility` | New skill | WCAG 2.1 AA baseline, semantic HTML, keyboard nav, colour contrast, automated a11y testing in CI. Applicable to projects with user-facing UI. |
| 16 | Create `mav-bp-environment-management` | New skill | Reproducible local dev, devcontainers/Docker Compose, .env patterns, onboarding speed, environment parity. |

### Low Priority (Supplements & Enhancements)

| # | Action | Type | Notes |
|---|--------|------|-------|
| 17 | Create `mav-bp-solutions-design` | New skill | Wrap `mav-create-solution-design` with universal principle. Persist designs as durable artifacts (ADRs, design docs). |
| 18 | Create `mav-bp-versioning` | New skill | SemVer, changelog maintenance, deprecation policy. Critical for libraries/SDKs, less urgent for internal apps. |
| 19 | Add Bitbucket Pipelines vendor skill | New skill | `mav-bp-cicd-bitbucket` for platform-specific monitoring. |
| 20 | Add multi-platform task tracking support | Enhancement | Jira, Linear, Azure Boards integration alongside GitHub Issues. |
| 21 | Enhance `mav-git-workflow` with remote validation | Skill update | Add explicit check that remote exists, fail if local-only. |

---

## Vendor Agnosticism Assessment

**Expectation:** Top-level best practices should be product/vendor agnostic.

| Skill | Vendor Agnostic? | Notes |
|-------|-------------------|-------|
| mav-bp-alerting | Yes | Principles only, no vendor lock-in |
| mav-bp-cicd | Yes | Platform-agnostic pipeline standards |
| mav-bp-cicd-github | No (by design) | Vendor-specific supplement — acceptable |
| mav-bp-cicd-gitlab | No (by design) | Vendor-specific supplement — acceptable |
| mav-bp-cicd-azure | No (by design) | Vendor-specific supplement — acceptable |
| mav-bp-linting | Yes | Language-specific, not vendor-specific |
| mav-bp-unit-testing | Yes | |
| mav-bp-integration-testing | Yes | |
| mav-bp-logging | Yes | |
| mav-git-workflow | Mostly | Git-specific (not SVN/Mercurial), but Git is universal enough |
| mav-github-issue-workflow | No | GitHub-only for task tracking |
| do-tech-docs | Yes | |
| mav-create-solution-design | Yes | |

**Verdict:** The existing best-practice skills (mav-bp-*) are properly vendor-agnostic. Vendor-specific skills exist as supplements, which is the correct pattern. The main concern is that task tracking and issue workflows are GitHub-only with no agnostic layer above them.

---

## Architecture Pattern Gap

There is a structural pattern gap worth noting. The expectation describes best practices as **universal principles**. Maverick currently has two types of skills that address these:

1. **Best-practice skills** (`mav-bp-*`) — principles and standards (non-invocable)
2. **Workflow skills** (`do-*`, `mav-create-*`) — operational procedures (invocable)

Some expected best practices only have workflow skills but lack a corresponding best-practice skill that establishes the *requirement*:

| Expected Practice | Has BP Skill? | Has Workflow Skill? | Gap |
|-------------------|---------------|---------------------|-----|
| Alerting | `mav-bp-alerting` | — | None |
| CI/CD | `mav-bp-cicd` | — | None |
| Linting | `mav-bp-linting` | — | None |
| Source Control | — | `mav-git-workflow` | Missing BP skill |
| Documentation | — | `do-tech-docs` | Missing BP skill |
| IaC | — | — | Missing both |
| Unit Testing | `mav-bp-unit-testing` | — | Coverage threshold gap |
| Integration Testing | `mav-bp-integration-testing` | — | Coverage threshold gap |
| Solutions Design | — | `mav-create-solution-design` | Missing BP skill |
| Task Tracking | — | `mav-create-tasks` | Missing BP skill |
| Application Security | — | — | Missing both |
| Dependency Management | — | — | Missing both |
| Observability | Partial (`mav-bp-logging` + `mav-bp-alerting`) | — | Missing unified BP skill |
| API Design | — | — | Missing both |
| Database Management | — | — | Missing both |
| Code Review | — | `agent-code-reviewer` | Missing BP skill |
| Error Handling | — | — | Missing both |
| Accessibility | — | — | Missing both |
| Environment Management | — | — | Missing both |
| Versioning & Deprecation | — | — | Missing both |

The recommendation is to create `mav-bp-*` skills for all practices marked "Missing BP skill" or "Missing both". These establish the principle/requirement, while workflow skills and agents handle the implementation. Priority order is reflected in the Priority Actions section above.

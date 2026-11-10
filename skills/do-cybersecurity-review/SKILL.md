---
name: do-cybersecurity-review
description: Audit a codebase for security risks in one of two modes. In full-audit mode it scans the entire codebase and writes a findings report to docs/security-audit.md (run as part of do-init or on demand). In update mode it hands a diff to the independent agent-security-reviewer, which reviews the diff plus the code it could impact in a fresh context and returns PASS, FINDINGS or BLOCKING. Applies the project's own security checklist from docs/maverick/skills/ and its invariant checks. Covers secrets exposure, dependency vulnerabilities, authentication and authorisation patterns, input validation, transport security, and common OWASP risks.
user-invocable: true
disable-model-invocation: false
context: fork
---

# Cybersecurity Review

Audit a codebase for security risks. Operates in two modes:

- **full-audit** — scan the entire codebase. Used by `do-init` at adoption time and on demand. Produces `docs/security-audit.md`. Flips `cybersecurity_reviewed` milestone.
- **update** — scoped to a diff, plus the code that could be impacted by the diff. Performed by the independent **agent-security-reviewer** in a fresh context, never by the agent that wrote the code. `do-issue-solo` and `do-issue-guided` dispatch that agent directly as the mandatory pre-PR gate. Does not flip the milestone (it's per-PR work, not a one-time milestone).

Refer to `mav-bp-application-security` for the standards each finding should be measured against. The skill **surfaces** risks; it does not modify code.

## Preflight (mandatory)

Run this **first**. If it exits non-zero, halt and report the stderr output to the user verbatim. Do not proceed.

```bash
uv run maverick preflight do-cybersecurity-review
```

The check verifies the project is initialised and `uv` is on PATH.

## Mode Selection

If `$ARGUMENTS` specifies a mode (`full-audit` or `update`), use it. If `update` is selected the caller must also pass a diff (via stdin or a file path); halt and ask for one if missing.

If no mode is specified, default to `full-audit`.

## Full Audit Mode

### 1. Detect the project stack

Identify language, framework, and runtime so subsequent checks know what to look for. Use the same detectors as `do-maverick-alignment`: `package.json`, `pyproject.toml`, `Dockerfile`, etc.

### 2. Load the project's own security checklist and checks

Generic categories miss the rules that matter most in a given codebase.
Read every project skill under `docs/maverick/skills/` whose name or
description concerns security, authorisation, tenancy, privacy,
personal data or compliance (e.g. `application-security`). Every rule
in them is an audit item: report each as PASS / WARN / FAIL / N/A in
the report's **Project checklist** section.

Then run the project's invariant checks and record the result:

```bash
uv run maverick checks run --base "$(uv run maverick git-workflow story-base)"
```

A failing check is a FAIL in the category it enforces.

### 3. Walk the audit categories

For each category below, search the codebase and assign one of:

- **PASS** — no concerns surfaced
- **WARN** — partial coverage or non-critical issues
- **FAIL** — material risk; needs human attention
- **N/A** — category does not apply to this project

#### 2.1 Secret exposure

Scan tracked files for committed credentials, tokens, private keys, and connection strings. Patterns to check (extend per stack):

- `AKIA[0-9A-Z]{16}` (AWS access key id), `aws_secret_access_key\s*=`
- `-----BEGIN (RSA |EC |OPENSSH )?PRIVATE KEY-----`
- `ghp_`, `gho_`, `ghs_`, `github_pat_` (GitHub tokens)
- `xox[baprs]-` (Slack tokens), `sk-` followed by 20+ alphanumerics (OpenAI/Anthropic-style)
- Generic `password\s*=\s*['"][^'"]+['"]`, `api[_-]?key\s*=\s*['"][^'"]+['"]`

Also check `.env*` files (any tracked) and history (`git log --all --full-history -- .env`).

#### 2.2 Dependency hygiene

| What | Where to look |
| --- | --- |
| Lock file present | `package-lock.json`, `pnpm-lock.yaml`, `yarn.lock`, `uv.lock`, `poetry.lock`, `Cargo.lock`, `go.sum` |
| Vulnerability scanning configured | `npm audit` in CI, `pip-audit`, `safety`, `cargo audit`, `trivy`, Dependabot, Renovate |
| Pinned versions | Direct deps pinned to a specific version or range |
| No supply-chain red flags | typosquats, abandoned packages, unfamiliar registries |

#### 2.3 Authentication and authorisation

- Where is auth implemented? Identify the library / pattern (Passport, NextAuth, Django auth, Spring Security, custom).
- Are passwords hashed with a modern algorithm (bcrypt, argon2, scrypt) — never plain SHA-x or MD5.
- Is session management correct (signed cookies, rotation on privilege change, secure + httponly + samesite flags)?
- Are routes/endpoints protected by middleware/decorators or do they require per-handler checks (latter is error-prone)?
- Are admin / privileged paths gated separately?

#### 2.4 Input validation and output encoding

- Are inputs validated at the boundary (schema validation: zod, pydantic, joi, Bean Validation)?
- Are templates auto-escaped (Jinja, JSX, Razor default-on)?
- Are SQL queries parameterised? Any string-concatenated SQL?
- Are file paths validated (no untrusted concat into `open()` / `fs.readFile`)?
- Are command invocations safe (no `shell=True` with untrusted input, no `eval`)?

#### 2.5 Transport, headers, and CORS

- Is HTTPS enforced (HSTS, redirect from HTTP, secure cookies)?
- Are baseline security headers set (CSP, X-Frame-Options or frame-ancestors, X-Content-Type-Options, Referrer-Policy, Permissions-Policy)?
- Is CORS scoped explicitly, not `*` for credentialed endpoints?

#### 2.6 Data at rest

- Is sensitive data encrypted at rest (DB-level, app-level)?
- Are backups encrypted?
- Is logging redacting PII / credentials? Search log calls for unredacted user input or auth headers.

#### 2.7 Logging, monitoring, and rate limiting

- Are auth failures logged with enough context to detect brute-force?
- Is there a rate-limit on login / password-reset / signup?
- Are alerts wired up for repeated auth failures, privilege escalations, or 5xx spikes?

#### 2.8 Container / infrastructure (if applicable)

- Does the Dockerfile run as a non-root user?
- Is the base image pinned by digest or just by tag?
- Is `.dockerignore` keeping `.env`, secrets, and `.git` out of layers?
- For IaC: are S3 buckets / blob stores private by default, encrypted, and versioned?

### 4. Write the report

Create `docs/security-audit.md` (create `docs/` if it doesn't exist). Use this structure:

```markdown
# Security Audit

**Generated:** <ISO timestamp>
**Stack detected:** <e.g., Node.js + Express, Python + Django>

## Summary

<1-2 sentences. Highest-severity finding. Headline risk.>

| Category | Status |
| --- | --- |
| Secret exposure | PASS / WARN / FAIL / N/A |
| Dependency hygiene | ... |
| Authentication / authorisation | ... |
| Input validation / output encoding | ... |
| Transport, headers, CORS | ... |
| Data at rest | ... |
| Logging, monitoring, rate limiting | ... |
| Container / infrastructure | ... |

## Project checklist

| Rule (source skill) | Status | Evidence |
| --- | --- | --- |
| <rule> (`docs/maverick/skills/<name>`) | PASS / WARN / FAIL / N/A | `path:line` |

<"No project security skill found" if there is none — and recommend
writing one with do-upskill.>

Project checks: <n configured, n failed — list failing commands>.

## Details

### <Category> — <STATUS>

<Evidence: file paths, snippets, dependency names. Be concrete.>

<If WARN/FAIL: a one-paragraph recommendation with a concrete next step.>

<repeat per category>

## Recommendations (prioritised)

1. **<Severity: high/medium/low>** — <action>. <File or area>. <Why it matters>.
2. ...

## Proposed invariant checks

<For each finding that a script could catch every time (a forbidden
call, a missing declaration, a grant that must not exist), propose a
check command and what it asserts. Reviewers miss repeat cases; a check
in `checks.commands` never does.>
```

Use one-line citations (`path/to/file:42`) so a human (or a follow-up agent) can jump straight to evidence.

### 5. Surface the findings to the user

After writing the report, print:

- The number of findings at each severity.
- The path to the report.
- A one-line top-recommendation if any FAIL exists.

### 6. Record the milestone

Once the report is written, record that the cybersecurity review has run on this project:

```bash
uv run maverick integration set cybersecurity_reviewed true
```

This commits the milestone into `.maverick/config.json` so other Maverick skills (and `maverick integration get`) can see it.

## Update Mode

Diff-scoped review used as the mandatory pre-PR security gate. It is
performed by **agent-security-reviewer**, a read-only agent
with a fresh context: the review must not run inside the context that
wrote the code, or the author is checking their own work.

`do-issue-solo` and `do-issue-guided` dispatch
the agent directly. If you were invoked in `update` mode (for example by
a user typing the command), do the same:

1. Build the diff (`git diff origin/<base>...HEAD > <file>`) if the
   caller didn't pass one.
2. Dispatch **agent-security-reviewer** with `Mode: diff`,
   the diff path, the base branch and a one-paragraph spec. Do not
   review the diff yourself.
3. Return the agent's JSON result and its `MAVERICK_SECURITY_VERDICT`
   line unchanged.

The agent's procedure (project checklist, invariant checks, impact set,
categories) and verdict semantics (PASS / FINDINGS / BLOCKING) are
defined in its own prompt. Update mode never writes to
`docs/security-audit.md`: its findings are transient and the caller
decides where they go.

## Rules

- **Surface, do not fix.** Report findings; do not modify code as part of this skill. Fixes are tracked work that go through `do-issue-solo` after the user prioritises them.
- **Cite evidence.** Every WARN / FAIL must reference a file path or dependency name. Vague findings ("auth could be stronger") are not actionable.
- **Be honest about coverage.** If a category requires runtime testing or production data the audit cannot reach, mark it N/A and note what would be needed for a thorough review.
- **Defer to mav-bp-application-security** for what "good" looks like in each category. This skill is the audit; that one is the standard.
- **Follow mav-scope-boundaries** — do not run anything that would modify production systems, change auth/permissions, or take destructive action.

## Return Protocol (update mode)

When invoked from `do-issue-solo` Phase 7 (or any other
caller) in `update` mode, `do-cybersecurity-review` is a
**subroutine of the calling workflow** — not a terminal action.
Returning the structured verdict is a hand-back to the caller's next
numbered step, not a phase-complete signal (#106).

When you return from this skill, **do not** post a closing summary, do
not stop. The calling workflow still owns, in order:

1. Closing the `skill-dispatch` interval that wrapped this invocation
   (`uv run maverick report end --auto … --outcome <success|failure|blocked>`).
   The outcome maps from the verdict: `PASS` → `success`,
   `FINDINGS` → `success` (with the findings folded into the PR body
   draft), `BLOCKING` → `blocked`.
2. Acting on the verdict — halting on `BLOCKING`, folding findings
   into the PR body draft on `FINDINGS`, or recording
   `Security review: no concerns.` on `PASS`.
3. Advancing to the next phase (open the PR) once the verdict has
   been folded in.

If you find yourself drafting a final summary after returning here,
that is the signal: scroll back to the calling workflow and resume
from the step immediately after the
`/do-cybersecurity-review` dispatch.

<!-- maverick-plugin-version: 5.2.2 -->

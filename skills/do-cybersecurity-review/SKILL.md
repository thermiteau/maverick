---
name: do-cybersecurity-review
description: Run a security audit of the project's existing codebase and write a findings report to docs/security-audit.md. Covers secrets exposure, dependency vulnerabilities, authentication and authorisation patterns, input validation, transport security, and common OWASP risks. Run as part of do-init or on demand.
user-invocable: true
disable-model-invocation: false
---

# Cybersecurity Review

Audit a codebase for security risks. Operates in two modes:

- **full-audit** — scan the entire codebase. Used by `do-init` at adoption time and on demand. Produces `docs/security-audit.md`. Flips `cybersecurity_reviewed` milestone.
- **update** — scoped to a diff, plus the code that could be impacted by the diff. Used by `do-issue-solo` and `do-issue-guided` as a mandatory pre-push gate before opening a PR. Returns a structured findings list to the orchestrator; does not flip the milestone (it's per-PR work, not a one-time milestone).

Refer to `mav-bp-application-security` for the standards each finding should be measured against. The skill **surfaces** risks; it does not modify code.

## Preflight (mandatory)

Run this **first**. If it exits non-zero, halt and report the stderr output to the user verbatim. Do not proceed.

```bash
uv run maverick preflight do-cybersecurity-review
```

The check verifies the project is initialised and `uv` is on PATH.

## Mode Selection

If `` specifies a mode (`full-audit` or `update`), use it. If `update` is selected the caller must also pass a diff (via stdin or a file path); halt and ask for one if missing.

If no mode is specified, default to `full-audit`.

## Full Audit Mode

### 1. Detect the project stack

Identify language, framework, and runtime so subsequent checks know what to look for. Use the same detectors as `do-maverick-alignment`: `package.json`, `pyproject.toml`, `Dockerfile`, etc.

### 2. Walk the audit categories

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

### 3. Write the report

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

## Details

### <Category> — <STATUS>

<Evidence: file paths, snippets, dependency names. Be concrete.>

<If WARN/FAIL: a one-paragraph recommendation with a concrete next step.>

<repeat per category>

## Recommendations (prioritised)

1. **<Severity: high/medium/low>** — <action>. <File or area>. <Why it matters>.
2. ...
```

Use one-line citations (`path/to/file:42`) so a human (or a follow-up agent) can jump straight to evidence.

### 4. Surface the findings to the user

After writing the report, print:

- The number of findings at each severity.
- The path to the report.
- A one-line top-recommendation if any FAIL exists.

### 5. Record the milestone

Once the report is written, record that the cybersecurity review has run on this project:

```bash
uv run maverick integration set cybersecurity_reviewed true
```

This commits the milestone into `.maverick/config.json` so other Maverick skills (and `maverick integration get`) can see it.

## Update Mode

Diff-scoped review used as a mandatory pre-push gate by `do-issue-solo` and `do-issue-guided`. Reviews **only the changed code and the code that could be impacted by it** — not the whole codebase. Returns findings to the orchestrator as a structured outcome.

This mode does **not** flip the `cybersecurity_reviewed` milestone — it runs on every PR, not once per project lifetime.

### 1. Read the diff

Caller passes the diff via stdin or as a file path. Parse it to get:

- the list of changed files
- the changed line ranges per file (so subsequent checks can be scoped)
- whether any of the changes touch dependency manifests (`package.json`, `pyproject.toml`, `Cargo.toml`, lock files), env / config files, IaC, or CI workflows — those carry security weight beyond the line count

If no diff was provided, halt and ask the caller for one. Do not silently fall back to a full-audit scan.

### 2. Identify impacted code

A change to a function, type, schema, or config can introduce security risk in code that wasn't itself edited. For each changed entity, identify the impact set:

| Change kind | Impact set to audit |
| --- | --- |
| Function signature / body | All callers (use grep / IDE-equivalent symbol search) |
| Exported type / schema | All importers; also serialisation / persistence sites |
| Auth / authz primitive (middleware, decorator, role) | Every route or handler protected by it |
| Public API surface (route, endpoint, GraphQL resolver) | Clients of that API; rate-limits and input validation around it |
| Config or env variable | Every reader of that config; consider whether the new value needs to be a secret |
| Dependency added or upgraded | The added/upgraded package itself: licence, known CVEs, transitive deps |
| Dockerfile / IaC | The deployed surface that uses it |

The impact set is **bounded** — do not transitively trace until the entire codebase is included. Stop at one or two hops; if the impact is wider than that, surface it as a finding ("this change has wide reach; recommend a fuller review") rather than try to audit everything.

### 3. Run the audit categories on the scoped set

Apply the same eight categories from Full Audit Mode (Secret exposure, Dependency hygiene, Authentication / authorisation, Input validation / output encoding, Transport / headers / CORS, Data at rest, Logging / monitoring / rate-limit, Container / IaC) — but only against the changed lines and the impact set, not the whole repo.

Most categories will be N/A on any given diff. That is fine. Returning "N/A" with a one-line justification is informative; returning empty findings without saying which categories were considered is not.

### 4. Return a structured outcome

The orchestrator wires this output into the PR description or a comment. Format:

```json
{
  "verdict": "PASS" | "FINDINGS" | "BLOCKING",
  "summary": "<one sentence: what was reviewed and the headline result>",
  "categories_considered": ["secret-exposure", "auth", ...],
  "findings": [
    {
      "severity": "critical|high|medium|low",
      "category": "<one of the eight>",
      "location": "<path/to/file:line>",
      "description": "<concrete what + why>",
      "recommendation": "<concrete next step>"
    }
  ]
}
```

Verdict semantics:

- **PASS** — nothing of concern. Findings list may still contain `low` severity items but none are actionable.
- **FINDINGS** — one or more `medium` / `high` items. The PR may proceed; findings are surfaced to the human reviewer in the PR body.
- **BLOCKING** — at least one `critical` finding (e.g., a secret committed to the diff, an auth bypass introduced). The orchestrator must halt the push and surface this to the user. Do not return BLOCKING lightly — the bar is "this PR cannot land safely as-is".

### 5. Do not write to docs/security-audit.md

Update mode produces transient findings, not a snapshot of the whole codebase. Writing to the audit doc would either overwrite valid full-audit content or accumulate noise. Findings stay in the structured output; the orchestrator decides where they end up.

## Rules

- **Surface, do not fix.** Report findings; do not modify code as part of this skill. Fixes are tracked work that go through `do-issue-solo` after the user prioritises them.
- **Cite evidence.** Every WARN / FAIL must reference a file path or dependency name. Vague findings ("auth could be stronger") are not actionable.
- **Be honest about coverage.** If a category requires runtime testing or production data the audit cannot reach, mark it N/A and note what would be needed for a thorough review.
- **Defer to mav-bp-application-security** for what "good" looks like in each category. This skill is the audit; that one is the standard.
- **Follow mav-scope-boundaries** — do not run anything that would modify production systems, change auth/permissions, or take destructive action.

<!-- maverick-plugin-version: 1.0.0 -->

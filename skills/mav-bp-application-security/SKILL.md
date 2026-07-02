---
name: mav-bp-application-security
description: Application security conventions for all projects. Covers OWASP Top 10 awareness, input validation, secrets management, dependency scanning, SAST/DAST integration, and security headers. Applied when writing or reviewing any code.
user-invocable: false
disable-model-invocation: true
---

# Application Security Standards

Ensure all code is written with security as a first-class design constraint, and that changes to the security surface stay within authorized scope.

## Maverick's Rules

- **Actively consider the current OWASP Top 10** on every change you write or review — do not enumerate from memory of an old list; check whether each current risk applies.
- **Secrets — hard rules**: never in source code, committed `.env` files, logs, error messages, or Docker image layers (`ENV`/`COPY`). `.env.example` documents variable names without values. If a secret is ever committed, rotate it immediately — removing it from git history is insufficient.
- **Secret scanning is mandatory**: pre-commit hooks (gitleaks, trufflehog, git-secrets) plus a CI gate on every PR and push.
- **SAST on every PR**, with critical/high findings build-breaking; tune rules — a noisy scanner gets ignored. DAST against staging at minimum on every deployment there, with findings tracked as issues.
- **Dependency scanning on every build**, failing on critical/high with an explicit exceptions process — see mav-bp-dependency-management.
- **Mask or redact sensitive data before logging** — see mav-bp-operability.
- **Secure defaults are non-negotiable**: TLS 1.2+ everywhere, parameterised queries as the default data-access method, `Secure`/`HttpOnly`/`SameSite` on all auth cookies, debug mode and verbose errors off in production, framework auto-escaping and CSRF middleware never disabled.
- **CSP**: start from `default-src 'self'`; avoid `unsafe-inline`/`unsafe-eval` (use nonces or hashes); deploy report-only before enforcing.
- **API security**: authenticate every endpoint unless explicitly public; always verify JWT signature, issuer, audience, and expiry; rate limit auth endpoints. See mav-bp-api-design.

**Scope authorization for security-surface work**: implementing or changing security headers, CORS policy, CSRF middleware, cookie flags, or password policy is allowed only when the issue explicitly authorizes it, and must always be flagged per `mav-scope-boundaries` — auth and security-surface changes are never silent drive-bys.

## Project Implementation Lookup

Check for `docs/maverick/skills/application-security/SKILL.md`. If present, read it and follow it — it wins on specifics (library, config, conventions). If missing, proceed with these standards and note the gap in your summary.

## Detecting Security Issues in Code Review

| Pattern                                                  | Issue                        | Fix                                                          |
| -------------------------------------------------------- | ---------------------------- | ------------------------------------------------------------ |
| User input concatenated into SQL query                   | SQL injection                | Use parameterised queries or prepared statements             |
| `innerHTML`, `dangerouslySetInnerHTML`, or `v-html` used | XSS vulnerability            | Use framework auto-escaping; sanitise with DOMPurify/bleach  |
| Hardcoded password, API key, or token in source          | Leaked secret                | Move to secrets manager; add pre-commit scanning             |
| `eval()`, `exec()`, or `Function()` with user input      | Code injection               | Remove eval; use safe alternatives                           |
| Password stored as plaintext or with MD5/SHA1            | Weak credential storage      | Use bcrypt, scrypt, or Argon2id                              |
| CSRF protection disabled or missing                      | Cross-site request forgery   | Enable framework CSRF middleware; add anti-CSRF tokens       |
| Missing authorisation check on endpoint                  | Broken access control        | Add authorisation middleware; check on every request         |
| `shell=True` or `os.system()` with user input            | Command injection            | Use subprocess with argument list; avoid shell execution     |
| Sensitive data in log output                             | Information leakage          | Mask or redact before logging                                |
| `.env` file committed to repository                      | Secret exposure              | Add to `.gitignore`; rotate exposed secrets                  |
| HTTP used instead of HTTPS                               | Man-in-the-middle risk       | Enforce TLS everywhere                                       |
| JWT signature not verified                               | Authentication bypass        | Always verify signature, issuer, audience, and expiry        |
| XML parser with external entities enabled                | XXE attack                   | Disable external entity processing; prefer JSON              |
| Missing rate limiting on login/auth endpoints            | Brute-force vulnerability    | Add rate limiting; implement account lockout                 |
| Wildcard CORS (`Access-Control-Allow-Origin: *`)         | Overly permissive CORS       | Restrict to specific allowed origins                         |
| Debug mode or verbose errors enabled in production       | Information disclosure       | Disable debug mode; return generic error messages            |
| File path constructed from user input without validation | Path traversal               | Canonicalise and validate against a safe base directory      |
| Deserialisation of untrusted data                        | Remote code execution        | Avoid deserialising untrusted input; use safe formats (JSON) |
| Missing `HttpOnly`/`Secure` flags on session cookies     | Session hijacking            | Set `HttpOnly`, `Secure`, and `SameSite` on all auth cookies |

<!-- maverick-plugin-version: 4.0.0 -->

---
name: mav-bp-environment-management
description: Environment management conventions for all projects. Covers reproducible local development, environment parity, .env patterns, developer onboarding, and containerised development. Applied when setting up or reviewing development environments.
user-invocable: false
disable-model-invocation: true
---

# Environment Management Standards

Maverick's hard rules for reproducible local development environments and environment-specific configuration.

## Maverick's Rules

- **Fresh clone to running app in under 30 minutes, via one setup command** — onboarding friction is a defect. Setup instructions must not require asking a team member; test them in CI or on a clean machine.
- **Pin everything** — language/tool versions (`.node-version`, `.tool-versions`, etc.) and container image versions (`postgres:16.2`, never `latest`).
- **No environment names in application code** — `if (env === "production")` is a code smell; one code path, config injected via env vars. Sole exception: a single log-verbosity/error-reporting config check at initialisation.
- **Database parity is non-negotiable** — same engine and major version locally (via Docker) as production. Never substitute SQLite for PostgreSQL in dev. Prefer real local service instances or emulators (LocalStack, Azurite); mock only as a last resort.
- **`.env` discipline** — `.env.example` is committed and lists every env var the application reads, each with a description; sensitive values blank, safe defaults provided. `.env` is gitignored. `.env.production` never exists locally — production config comes from the deployment platform. Validate required env vars at startup and fail fast.
- **Docker Compose** — bind ports to localhost only (`127.0.0.1:5432:5432`); include health checks so dependents wait for readiness.

`.env.example` format:

```bash
DATABASE_URL=              # PostgreSQL connection string (e.g., postgres://user:pass@localhost:5432/mydb)
STRIPE_API_KEY=            # Stripe secret key (starts with sk_test_ or sk_live_)
LOG_LEVEL=error            # error | warn | debug
PORT=3000                  # HTTP server port
```

## Project Implementation Lookup

Check for `docs/maverick/skills/environment-management/SKILL.md`. If present, read it — it wins on specifics (library, config, conventions). If missing, proceed with these standards and note the gap in your summary.

## Detecting Environment Management Issues in Code Review

| Pattern | Issue | Fix |
| ------- | ----- | --- |
| Hard-coded URLs, ports, or credentials in source code | Environment coupling | Extract to environment variables |
| `if (env === "production")` logic scattered in code | Environment branching | Use configuration values, not environment names |
| No `.env.example` but application reads env vars | Undocumented configuration | Create `.env.example` with all required vars |
| `.env` file committed to repository | Credential exposure risk | Add to `.gitignore`, remove from history |
| No version pinning for language runtime | Non-reproducible builds | Add `.node-version`, `.python-version`, or equivalent |
| `docker-compose.yml` using `latest` tags | Non-deterministic services | Pin to specific image versions |
| Setup instructions that require asking a team member | Tribal knowledge dependency | Document all steps in README or CONTRIBUTING.md |
| Database engine differs between dev and production | Environment parity violation | Use the same engine locally via Docker |
| No health checks in Docker Compose services | Startup race conditions | Add health checks and depends_on with condition |

## Boundaries

This skill covers local/dev environments only (devcontainers, Docker Compose for local services, `.env`, version pinning, onboarding). Deployed environments — Terraform, CloudFormation, Kubernetes, cloud provisioning — belong to `mav-bp-infrastructure-as-code`. When an artifact serves both (e.g., Compose used in local dev and CI), follow both.

<!-- maverick-plugin-version: 4.0.0 -->

---
name: mav-bp-environment-management
description: Environment management conventions for all projects. Covers reproducible local development, environment parity, .env patterns, developer onboarding, and containerised development. Applied when setting up or reviewing development environments.
disable-model-invocation: false
---

# Environment Management Standards

Ensure every project can be set up, run, and developed against reliably across machines and team members. Reproducible environments reduce onboarding time, eliminate "works on my machine" defects, and keep development aligned with production.

## Principles

1. **Reproducible from repo checkout** — cloning the repository and running a single setup command should produce a fully working local environment
2. **New developer to running app in <30 minutes** — onboarding friction is a defect. Measure it and fix it.
3. **Environment parity** — local development, CI, staging, and production should use the same language versions, dependency versions, and service configurations wherever possible
4. **Config via environment variables, not code** — environment-specific values (URLs, credentials, feature flags) are injected via env vars, never hard-coded or switched with code branches

## Project Implementation Lookup

Before applying these standards, load the project-specific environment management implementation:

```dot
digraph lookup {
    "docs/maverick/skills/environment-management/SKILL.md exists?" [shape=diamond];
    "Read and use alongside these standards" [shape=box];
    "Invoke upskill" [shape=box];
    "Read generated skill" [shape=box];

    "docs/maverick/skills/environment-management/SKILL.md exists?" -> "Read and use alongside these standards" [label="yes"];
    "docs/maverick/skills/environment-management/SKILL.md exists?" -> "Invoke upskill" [label="no"];
    "Invoke upskill" -> "Read generated skill";
    "Read generated skill" -> "Read and use alongside these standards";
}
```

1. Check for `docs/maverick/skills/environment-management/SKILL.md`
2. If missing, invoke the `do-upskill` skill with:
   - topic: environment-management
   - scan hints:
     - dependencies: docker, docker-compose, devcontainer, nix, vagrant, direnv, asdf, mise, nvm, pyenv, rbenv
     - grep: `devcontainer\.json|docker-compose|Vagrantfile|flake\.nix|\.envrc|\.tool-versions|\.node-version|\.python-version`
     - files: `.devcontainer/**`, `docker-compose*.yml`, `docker-compose*.yaml`, `Vagrantfile`, `flake.nix`, `.envrc`, `.tool-versions`, `.env.example`, `Dockerfile`
3. Read the project skill and apply these best practices in the context of the project's specific technology

## Local Development Reproducibility

Every project must have a documented, automated path from fresh clone to running application. Choose the approach that best fits the project's complexity:

| Approach | When to use | Example tooling |
| -------- | ----------- | --------------- |
| **Devcontainers** | Multi-service projects, complex dependencies, team standardisation | VS Code devcontainers, GitHub Codespaces |
| **Docker Compose** | Projects with external service dependencies (databases, caches, queues) | `docker-compose.yml` with app + services |
| **Language version managers** | Single-language projects with minimal external deps | nvm, pyenv, rbenv, asdf, mise, rustup |
| **Nix / Nix flakes** | Maximum reproducibility across OS and architecture | `flake.nix`, `shell.nix` |
| **Vagrant** | Projects requiring a full VM (OS-level dependencies, kernel modules) | `Vagrantfile` |

### Key Rules

- **Pin language and tool versions** — use `.node-version`, `.python-version`, `.tool-versions`, `rust-toolchain.toml`, or equivalent. Never rely on "whatever is installed on the developer's machine."
- **Automate dependency installation** — a single command (`make setup`, `./scripts/setup.sh`, `docker compose up`) should install all dependencies, seed databases, and start services.
- **Document prerequisites** — if the automated setup requires pre-installed tools (Docker, nvm, Xcode CLI tools), list them explicitly.
- **Test the setup path regularly** — onboarding scripts rot. Run them in CI or test them periodically on a clean machine.

## .env Management

Environment variables are the correct mechanism for injecting environment-specific configuration. The `.env` file pattern provides a convenient local interface to this mechanism.

### Rules

| File | Purpose | Committed to git? |
| ---- | ------- | ------------------ |
| `.env.example` | Template listing all required env vars with descriptions, no real values | Yes |
| `.env` | Developer's local values, populated from `.env.example` | No — must be in `.gitignore` |
| `.env.test` | Values for test runs, if distinct from development | Depends on whether values are sensitive |
| `.env.production` | Never exists locally — production config comes from the deployment platform | N/A |

### .env.example Format

```bash
# Database
DATABASE_URL=              # PostgreSQL connection string (e.g., postgres://user:pass@localhost:5432/mydb)
DATABASE_POOL_SIZE=10      # Connection pool size (default: 10)

# External services
STRIPE_API_KEY=            # Stripe secret key (starts with sk_test_ or sk_live_)
REDIS_URL=                 # Redis connection string (e.g., redis://localhost:6379)

# Application
LOG_LEVEL=debug            # error | warn | debug
PORT=3000                  # HTTP server port
```

### Key Rules

- **Every env var the application reads must appear in `.env.example`** — no undocumented environment variables
- **Include a brief description** for each variable so developers know what value to provide
- **Provide sensible defaults** where safe (ports, log levels, pool sizes) — leave sensitive values blank
- **Never commit real credentials** — not in `.env.example`, not in `.env`, not anywhere in the repository
- **Validate env vars at startup** — the application should fail fast with a clear message if required variables are missing

## Environment Parity

Differences between development and production environments cause defects that only appear after deployment. Minimise divergence:

| Dimension | Parity approach |
| --------- | --------------- |
| **Language version** | Pin the same version in dev (version manager), CI (workflow config), and production (Dockerfile / runtime config) |
| **Dependency versions** | Use lock files everywhere — same resolved versions in dev, CI, and production |
| **Database engine** | Use the same engine and major version locally (via Docker) as in production. Never substitute SQLite for PostgreSQL in dev. |
| **External services** | Run real service instances locally via Docker Compose where feasible. Use emulators (LocalStack, Azurite) when the real service is not available locally. Mock only as a last resort. |
| **OS and architecture** | Devcontainers or Docker minimise OS differences. Be aware of ARM vs x86 differences when developing on Apple Silicon targeting x86 production. |

### What is NOT Required to Match

- Scaling configuration (replica counts, instance sizes)
- Monitoring and alerting thresholds
- DNS, load balancer, and CDN configuration
- Production secrets and credentials

## Environment-Specific Configuration

Configuration that varies between environments must be supplied through environment variables or a configuration service — never through code branches.

### Anti-Patterns

```typescript
// BAD: Code branch per environment
if (process.env.NODE_ENV === "production") {
  db = connectTo("prod-db.internal:5432");
} else if (process.env.NODE_ENV === "staging") {
  db = connectTo("staging-db.internal:5432");
} else {
  db = connectTo("localhost:5432");
}

// GOOD: Single code path, configuration injected
db = connectTo(process.env.DATABASE_URL);
```

### Rules

- **One code path** — the application reads configuration from env vars or a config service. It does not know which environment it runs in.
- **No environment names in application code** — `if (env === "production")` is a code smell. The behaviour should be controlled by a feature flag or configuration value, not an environment name.
- **Exception: logging and error reporting** — it is acceptable to adjust log verbosity or error reporting detail based on an environment indicator, but this should be a single config check at initialisation, not scattered throughout the codebase.

## Container-Based Development

For projects with external dependencies (databases, caches, message queues, search engines), container-based development ensures every developer runs identical service versions.

### Docker Compose Guidelines

- Define all services the application depends on in `docker-compose.yml`
- Pin image versions — use `postgres:16.2`, not `postgres:latest`
- Use named volumes for data persistence across container restarts
- Expose ports only on localhost (`127.0.0.1:5432:5432`) to avoid conflicts and security exposure
- Include health checks so dependent services wait for readiness
- Provide a `make up` or `docker compose up` command that starts everything

### Devcontainer Guidelines

- Define the development container in `.devcontainer/devcontainer.json`
- Include all required tools, extensions, and settings in the container definition
- Use `postCreateCommand` or `postStartCommand` to run setup steps automatically
- Pin the base image version for reproducibility
- Test the devcontainer configuration in CI (e.g., build the container image as a CI step)

## Onboarding Documentation

Every project must have setup instructions that a new developer can follow without tribal knowledge.

### Required Content

| Section | Contents |
| ------- | -------- |
| **Prerequisites** | Required tools and versions (Docker, language runtime, etc.) with install instructions or links |
| **Setup steps** | Numbered, copy-pasteable commands from clone to running application |
| **Verification** | How to confirm the setup worked (e.g., "visit http://localhost:3000 and see the login page") |
| **Common issues** | Known setup problems and their solutions |
| **Seed data** | How to populate the local database with test data |

### Where to Put It

- **README.md** — if the setup is short (under 30 lines), include it directly
- **CONTRIBUTING.md** or **docs/development.md** — for longer setup guides, link from README

### Key Rules

- **Test the instructions** — run them on a clean machine or in CI. Stale instructions are worse than no instructions.
- **Keep them current** — update setup docs whenever the setup process changes. Include this in the PR review checklist.
- **Automate what you document** — if the instructions say "run these 5 commands", consider wrapping them in a `make setup` target.

## Relationship to Infrastructure as Code

This skill covers **local and development** environments — the developer's machine, CI runners, and local service dependencies.

The `mav-bp-infrastructure-as-code` skill covers **deployed environments** — cloud resources, servers, networking, and production infrastructure.

The boundary:
- **This skill**: devcontainers, Docker Compose for local services, .env files, language version pinning, onboarding scripts
- **Infrastructure as Code**: Terraform, CloudFormation, Kubernetes manifests, cloud resource provisioning

When both skills apply (e.g., a Docker Compose file used in both local dev and CI), follow the conventions from both.

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

<!-- maverick-plugin-version: 0.5.8-dev -->

from maverick.models import SkillConfig, TopicConfig
from maverick.names import (
    DO_UPSKILL,
    MAV_BP_ACCESSIBILITY,
    MAV_BP_API_DESIGN,
    MAV_BP_APPLICATION_SECURITY,
    MAV_BP_CICD,
    MAV_BP_DATABASE_MANAGEMENT,
    MAV_BP_DEPENDENCY_MANAGEMENT,
    MAV_BP_ENVIRONMENT_MANAGEMENT,
    MAV_BP_ERROR_HANDLING,
    MAV_BP_INFRASTRUCTURE_AS_CODE,
    MAV_BP_LINTING,
    MAV_BP_OPERABILITY,
    MAV_BP_TESTING,
)

# Shared hints for the two testing topics — one detection corpus.
_TESTING_DEPS = ["vitest", "jest", "mocha", "pytest", "unittest", "junit", "rspec"]
_TESTING_GREP = r"describe\(|it\(|test\(|expect\(|assert|@Test|func Test"
_TESTING_FILES = ["**/*.test.*", "**/*.spec.*", "**/test_*.*"]

TOPICS: list[TopicConfig] = [
    TopicConfig(
        topic="logging",
        prompt=(
            "Identify how logging is implemented in this codebase. Look for logger"
            " configuration, log levels, structured logging patterns, and where logs"
            " are sent. Use the logging best practice skill to guide the implementation."
        ),
        best_practice_skill=MAV_BP_OPERABILITY,
        scan_dependencies=[
            "pino", "winston", "bunyan", "log4js", "morgan", "structlog",
            "loguru", "slog", "tracing", "log4j", "slf4j",
        ],
        scan_grep=r"createLogger|getLogger|logger\.|console\.error|LOG_LEVEL|logging\.basicConfig",
        scan_files=["**/logger.*", "**/logging.*"],
    ),
    TopicConfig(
        topic="alerting",
        prompt=(
            "Identify how alerting is implemented in this codebase. Look for alert"
            " mechanisms, notification services, severity levels, and alert routing."
            " Use the alerting best practice skill to guide the implementation."
        ),
        best_practice_skill=MAV_BP_OPERABILITY,
        scan_dependencies=[
            "@aws-sdk/client-sns", "@pagerduty", "@opsgenie", "nodemailer",
            "sentry", "datadog",
        ],
        scan_grep=r"sendAlert|publish|PagerDuty|Opsgenie|alertService|notify|Sentry\.capture",
        scan_files=["**/alert*.*", "**/notify*.*"],
    ),
    TopicConfig(
        topic="unit-testing",
        prompt=(
            "Identify how unit testing is implemented in this codebase. Look for unit"
            " test frameworks, test runners, test coverage tools, and test data"
            " generation. Use the best practice skill to guide the implementation."
        ),
        best_practice_skill=MAV_BP_TESTING,
        scan_dependencies=_TESTING_DEPS,
        scan_grep=_TESTING_GREP,
        scan_files=_TESTING_FILES,
    ),
    TopicConfig(
        topic="integration-testing",
        prompt=(
            "Identify how integration testing is implemented in this codebase. Look"
            " for integration test frameworks, test runners, test coverage tools, and"
            " test data generation."
        ),
        best_practice_skill=MAV_BP_TESTING,
        scan_dependencies=_TESTING_DEPS,
        scan_grep=_TESTING_GREP,
        scan_files=_TESTING_FILES,
    ),
    TopicConfig(
        topic="linting",
        prompt=(
            "Identify how linting and code formatting is configured in this codebase."
            " Look for linter configs, formatter configs, pre-commit hooks, CI lint"
            " steps, and editor settings. Use the linting best practice skill to guide"
            " the implementation."
        ),
        best_practice_skill=MAV_BP_LINTING,
        scan_dependencies=[
            "eslint", "prettier", "ruff", "clippy", "golangci-lint", "rubocop",
            "stylelint", "lint-staged", "husky",
        ],
        scan_grep=r"eslint|prettier|ruff|lint-staged|formatOnSave|\"lint\":|\"format\":",
        scan_files=[
            "eslint.config.*", ".eslintrc*", ".prettierrc*", "prettier.config.*",
            "ruff.toml", ".golangci.yml", ".stylelintrc*",
        ],
    ),
    TopicConfig(
        topic="cicd",
        prompt=(
            "Identify which CI/CD platform this codebase uses. Check for GitHub Actions"
            " (.github/workflows/), GitLab CI (.gitlab-ci.yml), Azure DevOps"
            " (azure-pipelines.yml), and any other CI/CD configuration. Document the"
            " pipeline stages, quality gates, and deployment strategy. If the platform"
            " is detected, create a"
            " detailed project skill describing the specific platform's configuration,"
            " commands for monitoring pipeline status, common failure patterns, and"
            " platform boundaries. Use the CI/CD best practice skill to guide the"
            " implementation."
        ),
        best_practice_skill=MAV_BP_CICD,
        scan_grep=r"workflow_dispatch|on:\s+push|pipeline|stage|job|trigger:|pool:|vmImage:",
        scan_files=[
            ".github/workflows/*.yml", ".github/workflows/*.yaml", ".gitlab-ci.yml",
            "azure-pipelines.yml", "Jenkinsfile", ".circleci/config.yml",
            "buildkite.yml", ".buildkite/**/*.yml", "bitbucket-pipelines.yml",
            ".travis.yml", "cloudbuild.yaml", "appveyor.yml",
        ],
    ),
    TopicConfig(
        topic="application-security",
        prompt=(
            "Identify how application security is handled in this codebase. Look for"
            " input validation patterns, authentication/authorisation middleware,"
            " security headers, CSP configuration, secrets management, SAST/DAST"
            " tooling in CI, and dependency vulnerability scanning. Use the application"
            " security best practice skill to guide the implementation."
        ),
        best_practice_skill=MAV_BP_APPLICATION_SECURITY,
        scan_dependencies=[
            "helmet", "cors", "csurf", "express-rate-limit", "jsonwebtoken",
            "passport", "bcrypt", "argon2", "@auth0", "oidc-client", "snyk", "trivy",
        ],
        scan_grep=(
            r"helmet|csp|Content-Security-Policy|sanitize|escape|parameterized|"
            r"prepared|xss|csrf|cors|rateLimit|authenticate|authorize"
        ),
        scan_files=["**/security.*", "**/auth*.*", "**/middleware/auth*", "**/.snyk", "**/trivy*"],
    ),
    TopicConfig(
        topic="dependency-management",
        prompt=(
            "Identify how dependencies are managed in this codebase. Look for lock"
            " files, version pinning strategy, automated update tools (Dependabot,"
            " Renovate), vulnerability scanning in CI, and license compliance checks."
            " Use the dependency management best practice skill to guide the"
            " implementation."
        ),
        best_practice_skill=MAV_BP_DEPENDENCY_MANAGEMENT,
        scan_grep=r"dependabot|renovate|npm audit|pip-audit|safety check|license-checker|snyk test",
        scan_files=[
            ".github/dependabot.yml", "renovate.json", ".renovaterc*",
            "package-lock.json", "pnpm-lock.yaml", "yarn.lock", "uv.lock",
            "Cargo.lock", "go.sum", "Pipfile.lock", "poetry.lock",
        ],
    ),
    TopicConfig(
        topic="observability",
        prompt=(
            "Identify how observability is implemented in this codebase. Look for"
            " metrics collection, distributed tracing, health check endpoints,"
            " OpenTelemetry configuration, dashboard definitions, and SLI/SLO"
            " definitions. Use the observability best practice skill to guide the"
            " implementation."
        ),
        best_practice_skill=MAV_BP_OPERABILITY,
        scan_dependencies=[
            "@opentelemetry", "opentelemetry-sdk", "prometheus-client", "prom-client",
            "datadog", "newrelic", "elastic-apm-node", "dd-trace",
        ],
        scan_grep=(
            r"trace|span|metric|histogram|counter|gauge|healthCheck|health_check|"
            r"readiness|liveness|opentelemetry|prometheus"
        ),
        scan_files=[
            "**/tracing.*", "**/metrics.*", "**/health*.*", "**/telemetry.*",
            "**/instrumentation.*",
        ],
    ),
    TopicConfig(
        topic="api-design",
        prompt=(
            "Identify how APIs are designed in this codebase. Look for route"
            " definitions, API versioning patterns, error response formats, pagination"
            " implementations, OpenAPI/Swagger specs, and input validation middleware."
            " Use the API design best practice skill to guide the implementation."
        ),
        best_practice_skill=MAV_BP_API_DESIGN,
        scan_dependencies=[
            "swagger-ui-express", "@nestjs/swagger", "fastify-swagger",
            "drf-spectacular", "openapi", "tsoa",
        ],
        scan_grep=(
            r"@Api|@swagger|openapi|ApiResponse|ApiOperation|@route|@controller|"
            r"router\.|app\.get|app\.post"
        ),
        scan_files=[
            "**/openapi.*", "**/swagger.*", "**/api-docs*", "**/routes/**",
            "**/controllers/**",
        ],
    ),
    TopicConfig(
        topic="database",
        prompt=(
            "Identify how databases are managed in this codebase. Look for migration"
            " files, ORM configuration, connection pooling setup, seed data, backup"
            " scripts, and schema definitions. Use the database management best"
            " practice skill to guide the implementation."
        ),
        best_practice_skill=MAV_BP_DATABASE_MANAGEMENT,
        scan_dependencies=[
            "prisma", "drizzle", "knex", "sequelize", "typeorm", "sqlalchemy",
            "diesel", "gorm",
        ],
        scan_grep=r"createConnection|getRepository|prisma\.|db\.|migrate|schema",
        scan_files=["**/schema.*", "**/migration*", "**/database.*", "**/db.*"],
    ),
    TopicConfig(
        topic="error-handling",
        prompt=(
            "Identify how errors are handled in this codebase. Look for error classes,"
            " global error handlers, retry logic, circuit breaker patterns, error"
            " boundaries, and error response formatting. Use the error handling best"
            " practice skill to guide the implementation."
        ),
        best_practice_skill=MAV_BP_ERROR_HANDLING,
        scan_dependencies=[
            "http-errors", "boom", "@hapi/boom", "express-async-errors", "neverthrow",
        ],
        scan_grep=(
            r"ErrorBoundary|error_handler|errorHandler|globalExceptionFilter|"
            r"circuit.?breaker|retry|backoff|AppError|HttpException|ApiError"
        ),
        scan_files=["**/error*.*", "**/exception*.*", "**/middleware/error*"],
    ),
    TopicConfig(
        topic="infrastructure-as-code",
        prompt=(
            "Identify how infrastructure is managed in this codebase. Look for"
            " Terraform files, CloudFormation templates, Pulumi programs, Ansible"
            " playbooks, Docker Compose files, Kubernetes manifests, and any IaC"
            " configuration. If no IaC is found, check for runbook documentation."
            " Use the IaC best practice skill to guide the implementation."
        ),
        best_practice_skill=MAV_BP_INFRASTRUCTURE_AS_CODE,
        scan_grep=r"resource\s|provider\s|terraform|pulumi|cloudformation|ansible|helm",
        scan_files=[
            "*.tf", "*.tfvars", "Pulumi.yaml", "template.yaml", "template.json",
            "**/ansible/**", "**/helm/**", "docker-compose*.yml", "**/k8s/**",
            "**/kubernetes/**",
        ],
    ),
    TopicConfig(
        topic="accessibility",
        prompt=(
            "Identify how accessibility is handled in this codebase. Look for ARIA"
            " attributes, semantic HTML patterns, a11y testing tools in CI (axe-core,"
            " pa11y, Lighthouse), keyboard navigation handling, and focus management."
            " Use the accessibility best practice skill to guide the implementation."
        ),
        best_practice_skill=MAV_BP_ACCESSIBILITY,
        scan_dependencies=[
            "axe-core", "@axe-core/react", "pa11y", "lighthouse", "jest-axe",
            "@testing-library/jest-dom", "eslint-plugin-jsx-a11y",
        ],
        scan_grep=(
            r"aria-|role=|alt=|tabIndex|focusTrap|skipNav|screen\.getByRole|"
            r"toBeAccessible|axe"
        ),
        scan_files=["**/a11y*.*", "**/accessibility*.*", ".pa11yci*", "lighthouserc*"],
    ),
    TopicConfig(
        topic="environment-management",
        prompt=(
            "Identify how development environments are managed in this codebase. Look"
            " for devcontainer configuration, Docker Compose for local development,"
            " .env.example files, setup scripts, and onboarding documentation. Use the"
            " environment management best practice skill to guide the implementation."
        ),
        best_practice_skill=MAV_BP_ENVIRONMENT_MANAGEMENT,
        scan_dependencies=["dotenv", "python-dotenv", "django-environ", "envalid", "joi"],
        scan_grep=r"dotenv|process\.env|os\.environ|docker-compose|devcontainer|CONTRIBUTING",
        scan_files=[
            ".env.example", ".env.sample", ".env.template", ".devcontainer/**",
            "docker-compose*.yml", "Vagrantfile", "flake.nix", "shell.nix",
            "CONTRIBUTING.md",
        ],
    ),
]


def _scan_hints_markdown(topics: list[TopicConfig]) -> str:
    """Render the per-topic scan hints for the skill body.

    Generated from TOPICS so the body, topics.json, and any referencing
    skill share one detection corpus.
    """
    out: list[str] = []
    for t in topics:
        out.append(f"### {t.topic}\n")
        deps = ", ".join(t.scan_dependencies) if t.scan_dependencies else "N/A (not package-based)"
        out.append(f"- **dependencies**: {deps}")
        if t.scan_grep:
            out.append(f"- **grep**: `{t.scan_grep}`")
        if t.scan_files:
            out.append("- **files**: " + ", ".join(f"`{f}`" for f in t.scan_files))
        out.append("")
    return "\n".join(out).rstrip()


CONFIG = SkillConfig(
    name=DO_UPSKILL,
    description=(
        "Generate project-specific implementation skills at docs/maverick/skills/<topic>/SKILL.md by scanning the codebase. Pass a topic name to generate one topic; omit arguments to process every topic."
    ),
    argument_hint="topic (optional — omit to process all topics)",
    user_invocable=True,
    disable_model_invocation=False,
    extra_context={"SCAN_HINTS": _scan_hints_markdown(TOPICS)},
)

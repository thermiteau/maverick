from maverick.models import SkillConfig, TopicConfig
from maverick.names import (
    DO_UPSKILL,
    MAV_BP_ACCESSIBILITY,
    MAV_BP_ALERTING,
    MAV_BP_API_DESIGN,
    MAV_BP_APPLICATION_SECURITY,
    MAV_BP_CICD,
    MAV_BP_DATABASE_MANAGEMENT,
    MAV_BP_DEPENDENCY_MANAGEMENT,
    MAV_BP_ENVIRONMENT_MANAGEMENT,
    MAV_BP_ERROR_HANDLING,
    MAV_BP_INFRASTRUCTURE_AS_CODE,
    MAV_BP_INTEGRATION_TESTING,
    MAV_BP_LINTING,
    MAV_BP_LOGGING,
    MAV_BP_OBSERVABILITY,
    MAV_BP_UNIT_TESTING,
)

CONFIG = SkillConfig(
    name=DO_UPSKILL,
    description=(
        "Use when a best-practice skill needs project-specific implementation details and no project skill exists at docs/maverick/skills/<topic>/SKILL.md. Scans the codebase and generates a project-specific skill file."
    ),
    user_invocable=True,
    disable_model_invocation=False,
    depends_on=[],
)

TOPICS: list[TopicConfig] = [
    TopicConfig(
        topic="logging",
        prompt=(
            "Identify how logging is implemented in this codebase. Look for logger"
            " configuration, log levels, structured logging patterns, and where logs"
            " are sent. Use the logging best practice skill to guide the implementation."
        ),
        best_practice_skill=MAV_BP_LOGGING,
    ),
    TopicConfig(
        topic="alerting",
        prompt=(
            "Identify how alerting is implemented in this codebase. Look for alert"
            " mechanisms, notification services, severity levels, and alert routing."
            " Use the alerting best practice skill to guide the implementation."
        ),
        best_practice_skill=MAV_BP_ALERTING,
    ),
    TopicConfig(
        topic="unit-testing",
        prompt=(
            "Identify how unit testing is implemented in this codebase. Look for unit"
            " test frameworks, test runners, test coverage tools, and test data"
            " generation. Use the best practice skill to guide the implementation."
        ),
        best_practice_skill=MAV_BP_UNIT_TESTING,
    ),
    TopicConfig(
        topic="integration-testing",
        prompt=(
            "Identify how integration testing is implemented in this codebase. Look"
            " for integration test frameworks, test runners, test coverage tools, and"
            " test data generation."
        ),
        best_practice_skill=MAV_BP_INTEGRATION_TESTING,
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
    ),
    TopicConfig(
        topic="cicd",
        prompt=(
            "Identify which CI/CD platform this codebase uses. Check for GitHub Actions"
            " (.github/workflows/), GitLab CI (.gitlab-ci.yml), Azure DevOps"
            " (azure-pipelines.yml), and any other CI/CD configuration. Document the"
            " pipeline stages, quality gates, and deployment strategy. If the platform"
            " is GitHub Actions, GitLab CI, or Azure DevOps, also note which"
            " platform-specific skill applies (mav-bp-cicd-github, mav-bp-cicd-gitlab,"
            " or mav-bp-cicd-azure). If the platform is none of these three, create a"
            " detailed project skill describing the specific platform's configuration,"
            " commands for monitoring pipeline status, common failure patterns, and"
            " platform boundaries. Use the CI/CD best practice skill to guide the"
            " implementation."
        ),
        best_practice_skill=MAV_BP_CICD,
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
        best_practice_skill=MAV_BP_OBSERVABILITY,
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
    ),
]

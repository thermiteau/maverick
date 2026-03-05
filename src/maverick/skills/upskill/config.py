from maverick.models import SkillConfig, TopicConfig
from maverick.names import (
    MAV_BP_ALERTING,
    MAV_BP_CICD,
    MAV_BP_INTEGRATION_TESTING,
    MAV_BP_LINTING,
    MAV_BP_LOGGING,
    MAV_BP_UNIT_TESTING,
    UPSKILL,
)

CONFIG = SkillConfig(
    name=UPSKILL,
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
]

from maverick.models import SkillConfig
from maverick.names import DO_MAVERICK_ALIGNMENT

CONFIG = SkillConfig(
    name=DO_MAVERICK_ALIGNMENT,
    description=(
        "Analyze a project's codebase against Maverick standard practices and write a findings report. Checks linting, unit tests, integration tests, documentation, CI/CD, security, dependency management, observability, source control, and more. Run when onboarding an existing project or on demand."
    ),
    user_invocable=True,
    # Runs in an isolated forked context: the audit/setup work is
    # self-contained and would otherwise pollute the caller's window
    # (the #106 premature-stop class). The body is the fork's prompt.
    context="fork",
    disable_model_invocation=False,
)

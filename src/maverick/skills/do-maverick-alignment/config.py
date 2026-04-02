from maverick.models import SkillConfig
from maverick.names import DO_MAVERICK_ALIGNMENT

CONFIG = SkillConfig(
    name=DO_MAVERICK_ALIGNMENT,
    description=(
        "Analyze a project's codebase against Maverick standard practices and write a findings report. Checks linting, unit tests, integration tests, documentation, CI/CD, security, dependency management, observability, source control, and more. Run when onboarding an existing project or on demand."
    ),
    user_invocable=True,
    disable_model_invocation=False,
)

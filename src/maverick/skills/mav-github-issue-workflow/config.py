from maverick.models import SkillConfig
from maverick.names import MAV_GITHUB_ISSUE_WORKFLOW

CONFIG = SkillConfig(
    name=MAV_GITHUB_ISSUE_WORKFLOW,
    description=(
        "Standard patterns for interacting with GitHub issues — reading, commenting, updating, state tracking, branching, and PR creation. Use as a dependency from workflow skills, not directly."
    ),
    user_invocable=False,
    disable_model_invocation=False,
    depends_on=[],
)

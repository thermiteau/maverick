from maverick.models import SkillConfig
from maverick.names import TASK_BREAKDOWN

CONFIG = SkillConfig(
    name=TASK_BREAKDOWN,
    description=(
        "Decomposes a large implementation plan into independently trackable"
        " sub-tasks with dependency ordering and file ownership tracking."
        " Invoked by workflow skills when a plan exceeds the scope threshold."
    ),
    user_invocable=False,
    disable_model_invocation=False,
)

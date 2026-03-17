from maverick.models import SkillConfig
from maverick.names import MAV_CREATE_TASKS

CONFIG = SkillConfig(
    name=MAV_CREATE_TASKS,
    description=(
        "How to decompose a solution design into discrete, independently"
        " implementable tasks. Used as a dependency from workflow skills."
    ),
    user_invocable=False,
    disable_model_invocation=False,
)

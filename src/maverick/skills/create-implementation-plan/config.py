from maverick.models import SkillConfig
from maverick.names import CREATE_IMPLEMENTATION_PLAN

CONFIG = SkillConfig(
    name=CREATE_IMPLEMENTATION_PLAN,
    description=(
        "How to break a solution design into granular, verifiable implementation steps"
        " with scope control. Used as a dependency from workflow skills."
    ),
    user_invocable=True,
    disable_model_invocation=False,
)

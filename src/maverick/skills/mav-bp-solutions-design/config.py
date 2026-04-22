from maverick.models import SkillConfig
from maverick.names import MAV_BP_SOLUTIONS_DESIGN

CONFIG = SkillConfig(
    name=MAV_BP_SOLUTIONS_DESIGN,
    description=(
        "Solutions design conventions for all projects. Covers the requirement for design before implementation, design documentation persistence, requirements traceability, and Architecture Decision Records. Applied before starting implementation of any non-trivial change."
    ),
    user_invocable=False,
    disable_model_invocation=False,
    depends_on=[],
)

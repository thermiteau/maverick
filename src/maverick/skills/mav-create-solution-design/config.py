from maverick.models import SkillConfig
from maverick.names import MAV_CREATE_SOLUTION_DESIGN

CONFIG = SkillConfig(
    name=MAV_CREATE_SOLUTION_DESIGN,
    description=(
        "How to produce a solution design for a GitHub issue or task. Covers codebase"
        " exploration, design structure, and validation. Used as a dependency from"
        " workflow skills."
    ),
    user_invocable=True,
    disable_model_invocation=True,
)

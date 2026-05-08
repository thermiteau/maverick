from maverick.models import SkillConfig
from maverick.names import MAV_BP_CODE_REVIEW

CONFIG = SkillConfig(
    name=MAV_BP_CODE_REVIEW,
    description=(
        "Code review conventions for all projects. Covers mandatory review requirements, review scope, PR sizing, reviewer and author responsibilities, and automated review integration. Applied when creating or reviewing pull requests."
    ),
    user_invocable=False,
    disable_model_invocation=True,
    depends_on=[],
)

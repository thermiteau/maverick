from maverick.models import SkillConfig
from maverick.names import MAV_BP_DOCUMENTATION

CONFIG = SkillConfig(
    name=MAV_BP_DOCUMENTATION,
    description=(
        "Documentation conventions for all projects. Covers minimum documentation requirements, documentation freshness enforcement, AI-readable structure, and the relationship between human and machine audiences. Applied when creating or reviewing project documentation."
    ),
    user_invocable=False,
    disable_model_invocation=False,
    depends_on=[],
)

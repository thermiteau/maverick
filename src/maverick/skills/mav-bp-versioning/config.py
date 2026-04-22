from maverick.models import SkillConfig
from maverick.names import MAV_BP_VERSIONING

CONFIG = SkillConfig(
    name=MAV_BP_VERSIONING,
    description=(
        "Versioning and deprecation conventions for projects producing libraries, APIs, or SDKs. Covers semantic versioning, changelog maintenance, deprecation policies, and breaking change management. Applied when releasing or reviewing versioned artifacts."
    ),
    user_invocable=False,
    disable_model_invocation=False,
    depends_on=[],
)

from maverick.models import SkillConfig
from maverick.names import MAV_BP_API_DESIGN

CONFIG = SkillConfig(
    name=MAV_BP_API_DESIGN,
    description=(
        "API design conventions for projects with API surfaces. Covers REST and GraphQL standards, versioning, error formats, pagination, documentation as code, and backwards compatibility. Applied when designing, implementing, or reviewing APIs."
    ),
    user_invocable=False,
    disable_model_invocation=False,
    depends_on=[],
)

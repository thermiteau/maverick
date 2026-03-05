from maverick.models import SkillConfig
from maverick.names import MAV_BP_CICD

CONFIG = SkillConfig(
    name=MAV_BP_CICD,
    description=(
        "Platform-agnostic CI/CD conventions. Covers pipeline stages, quality gates, environment promotion, secrets management, artifact handling, and deployment boundaries. Applied when configuring or reviewing CI/CD pipelines."
    ),
    user_invocable=False,
    disable_model_invocation=False,
    depends_on=[],
)

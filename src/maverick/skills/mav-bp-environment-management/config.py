from maverick.models import SkillConfig
from maverick.names import MAV_BP_ENVIRONMENT_MANAGEMENT

CONFIG = SkillConfig(
    name=MAV_BP_ENVIRONMENT_MANAGEMENT,
    description=(
        "Environment management conventions for all projects. Covers reproducible local development, environment parity, .env patterns, developer onboarding, and containerised development. Applied when setting up or reviewing development environments."
    ),
    user_invocable=False,
    disable_model_invocation=False,
    depends_on=[],
)

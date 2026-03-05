from maverick.models import SkillConfig
from maverick.names import MAV_BP_LOGGING

CONFIG = SkillConfig(
    name=MAV_BP_LOGGING,
    description=(
        "Logging conventions for backend and frontend applications. Covers log levels, structured logging, centralised aggregation, and project logging guidance. Applied when writing or reviewing code that includes logging."
    ),
    user_invocable=False,
    disable_model_invocation=False,
    depends_on=[],
)

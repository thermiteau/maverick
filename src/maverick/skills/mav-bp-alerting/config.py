from maverick.models import SkillConfig
from maverick.names import MAV_BP_ALERTING

CONFIG = SkillConfig(
    name=MAV_BP_ALERTING,
    description=(
        "Alerting conventions for fatal errors in applications. Covers severity levels, alert context, centralised notification, and project alerting guidance. Applied when writing error handling or reviewing code."
    ),
    user_invocable=False,
    disable_model_invocation=False,
    depends_on=[],
)

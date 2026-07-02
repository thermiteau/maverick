from maverick.models import SkillConfig
from maverick.names import MAV_BP_OPERABILITY

CONFIG = SkillConfig(
    name=MAV_BP_OPERABILITY,
    description=(
        "Operability standards — logging, alerting, and observability as one "
        "discipline. Maverick's opinionated rules: error-only log levels (no "
        "info), structured JSON logs, alert-at-the-boundary, correlation across "
        "logs/metrics/traces. Applied when writing or reviewing code that "
        "logs, alerts, or instruments."
    ),
    user_invocable=False,
    disable_model_invocation=True,
)

from maverick.models import SkillConfig
from maverick.names import MAV_BP_OBSERVABILITY

CONFIG = SkillConfig(
    name=MAV_BP_OBSERVABILITY,
    description=(
        "Observability conventions for deployed applications. Covers metrics collection, distributed tracing, health checks, SLIs/SLOs, and dashboards. Complements the logging and alerting skills to complete the observability picture. Applied when designing or reviewing operational aspects of services."
    ),
    user_invocable=False,
    disable_model_invocation=True,
    depends_on=[],
)

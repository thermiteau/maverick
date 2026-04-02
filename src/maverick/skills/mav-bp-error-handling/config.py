from maverick.models import SkillConfig
from maverick.names import MAV_BP_ERROR_HANDLING

CONFIG = SkillConfig(
    name=MAV_BP_ERROR_HANDLING,
    description=(
        "Error handling conventions for all applications. Covers error propagation, retry strategies, circuit breakers, graceful degradation, error boundaries, and typed errors. Applied when writing or reviewing error handling code."
    ),
    user_invocable=False,
    disable_model_invocation=False,
    depends_on=[],
)

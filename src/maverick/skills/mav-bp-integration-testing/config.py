from maverick.models import SkillConfig
from maverick.names import MAV_BP_INTEGRATION_TESTING

CONFIG = SkillConfig(
    name=MAV_BP_INTEGRATION_TESTING,
    description=(
        "Integration testing conventions for applications. Covers test scope, external dependency management, environment setup, data isolation, and project testing guidance. Applied when writing or reviewing integration tests."
    ),
    user_invocable=False,
    disable_model_invocation=False,
    depends_on=[],
)

from maverick.models import SkillConfig
from maverick.names import MAV_BP_UNIT_TESTING

CONFIG = SkillConfig(
    name=MAV_BP_UNIT_TESTING,
    description=(
        "Unit testing conventions for applications. Covers test design, isolation, structure, mocking discipline, and project testing guidance. Applied when writing or reviewing unit tests."
    ),
    user_invocable=False,
    disable_model_invocation=False,
    depends_on=[],
)

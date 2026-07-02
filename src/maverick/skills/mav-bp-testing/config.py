from maverick.models import SkillConfig
from maverick.names import MAV_BP_TESTING

CONFIG = SkillConfig(
    name=MAV_BP_TESTING,
    description=(
        "Testing standards — unit and integration testing as one discipline. "
        "Maverick's opinionated rules: behaviour over implementation, mock at "
        "boundaries only, 60% unit-coverage CI gate, critical-path integration "
        "coverage with a no-decrease ratchet. Applied when writing or "
        "reviewing tests."
    ),
    user_invocable=False,
    disable_model_invocation=True,
)

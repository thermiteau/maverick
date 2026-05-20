from maverick.models import SkillConfig
from maverick.names import (
    DO_TEST,
    MAV_BP_INTEGRATION_TESTING,
    MAV_BP_UNIT_TESTING,
    MAV_LOCAL_VERIFICATION,
    MAV_SCOPE_BOUNDARIES,
)

CONFIG = SkillConfig(
    name=DO_TEST,
    description=(
        "Write or update tests for a code change. Operates in two modes:"
        " `unit` (module-scoped, fast, deterministic) and `integration`"
        " (crosses module / service / database boundaries). Intended to be"
        " invoked once per testable change from inside a do-issue-* or"
        " do-epic phase. Mode is required."
    ),
    argument_hint="mode: unit or integration",
    user_invocable=True,
    disable_model_invocation=False,
    depends_on=[
        MAV_BP_UNIT_TESTING,
        MAV_BP_INTEGRATION_TESTING,
        MAV_LOCAL_VERIFICATION,
        MAV_SCOPE_BOUNDARIES,
    ],
)

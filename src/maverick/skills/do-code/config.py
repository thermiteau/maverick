from maverick.models import SkillConfig
from maverick.names import (
    DO_CODE,
    MAV_BP_APPLICATION_SECURITY,
    MAV_BP_ERROR_HANDLING,
    MAV_BP_OPERABILITY,
    MAV_LOCAL_VERIFICATION,
    MAV_SCOPE_BOUNDARIES,
    MAV_SYSTEMATIC_DEBUGGING,
)

CONFIG = SkillConfig(
    name=DO_CODE,
    description=(
        "Implement a focused code change. Use this skill as the wrapper for"
        " any implementation work so the Maverick workflow report captures"
        " what was done and so the agent applies the project's coding"
        " standards before editing. Intended to be invoked once per task"
        " from inside a do-issue-* or do-epic phase, not standalone."
    ),
    argument_hint="brief description of the task (one line)",
    user_invocable=True,
    disable_model_invocation=False,
    depends_on=[
        MAV_BP_ERROR_HANDLING,
        MAV_BP_OPERABILITY,
        MAV_BP_APPLICATION_SECURITY,
        MAV_LOCAL_VERIFICATION,
        MAV_SCOPE_BOUNDARIES,
        MAV_SYSTEMATIC_DEBUGGING,
    ],
)

from maverick.models import SkillConfig
from maverick.names import (
    CREATE_IMPLEMENTATION_PLAN,
    CREATE_SOLUTION_DESIGN,
    DO_TASK_SOLO,
    MAV_BP_ALERTING,
    MAV_BP_CICD,
    MAV_BP_LOGGING,
    MAV_CLAUDE_CODE_RECOVERY,
    MAV_GIT_WORKFLOW,
    MAV_LOCAL_VERIFICATION,
    MAV_PLAN_EXECUTION,
    MAV_SCOPE_BOUNDARIES,
    MAV_SYSTEMATIC_DEBUGGING,
    PULLREQUEST_REVIEW,
    TASK_BREAKDOWN,
)

CONFIG = SkillConfig(
    name=DO_TASK_SOLO,
    description=(
        "Work on a user-described task end-to-end autonomously using local task"
        " files instead of GitHub issues. The user describes what they want"
        " interactively, and Claude formalises, designs, plans, and implements it."
    ),
    argument_hint="short task description (optional — will prompt if missing)",
    user_invocable=True,
    disable_model_invocation=False,
    depends_on=[
        MAV_SCOPE_BOUNDARIES,
        MAV_GIT_WORKFLOW,
        CREATE_SOLUTION_DESIGN,
        CREATE_IMPLEMENTATION_PLAN,
        TASK_BREAKDOWN,
        MAV_PLAN_EXECUTION,
        MAV_LOCAL_VERIFICATION,
        MAV_BP_CICD,
        MAV_CLAUDE_CODE_RECOVERY,
        MAV_BP_LOGGING,
        MAV_BP_ALERTING,
        MAV_SYSTEMATIC_DEBUGGING,
        PULLREQUEST_REVIEW,
    ],
)

from maverick.models import SkillConfig
from maverick.names import (
    CREATE_IMPLEMENTATION_PLAN,
    CREATE_SOLUTION_DESIGN,
    DO_ISSUE_GUIDED,
    MAV_BP_ALERTING,
    MAV_BP_CICD,
    MAV_BP_LOGGING,
    MAV_CLAUDE_CODE_RECOVERY,
    MAV_GIT_WORKFLOW,
    MAV_GITHUB_ISSUE_WORKFLOW,
    MAV_LOCAL_VERIFICATION,
    MAV_PLAN_EXECUTION,
    MAV_SCOPE_BOUNDARIES,
    MAV_SYSTEMATIC_DEBUGGING,
    PULLREQUEST_REVIEW,
)

CONFIG = SkillConfig(
    name=DO_ISSUE_GUIDED,
    description=(
        "Work on a GitHub issue interactively with the user. Proceeds autonomously"
        " through routine work but pauses for confirmation at key decision points"
        " and when uncertain."
    ),
    argument_hint="issue number (e.g., 123)",
    user_invocable=True,
    disable_model_invocation=False,
    depends_on=[
        MAV_SCOPE_BOUNDARIES,
        MAV_GIT_WORKFLOW,
        MAV_GITHUB_ISSUE_WORKFLOW,
        CREATE_SOLUTION_DESIGN,
        CREATE_IMPLEMENTATION_PLAN,
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

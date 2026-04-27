from maverick.models import SkillConfig
from maverick.names import (
    DO_DOCS,
    DO_ISSUE_GUIDED,
    DO_PULLREQUEST_REVIEW,
    MAV_BP_ALERTING,
    MAV_BP_CICD,
    MAV_BP_LOGGING,
    MAV_CLAUDE_CODE_RECOVERY,
    MAV_CREATE_SOLUTION_DESIGN,
    MAV_CREATE_TASKS,
    MAV_GIT_WORKFLOW,
    MAV_GITHUB_ISSUE_WORKFLOW,
    MAV_LOCAL_VERIFICATION,
    MAV_PLAN_EXECUTION,
    MAV_SCOPE_BOUNDARIES,
    MAV_SYSTEMATIC_DEBUGGING,
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
        MAV_CREATE_SOLUTION_DESIGN,
        MAV_CREATE_TASKS,
        MAV_PLAN_EXECUTION,
        MAV_LOCAL_VERIFICATION,
        MAV_BP_CICD,
        MAV_CLAUDE_CODE_RECOVERY,
        MAV_BP_LOGGING,
        MAV_BP_ALERTING,
        MAV_SYSTEMATIC_DEBUGGING,
        DO_DOCS,
        DO_PULLREQUEST_REVIEW,
    ],
)

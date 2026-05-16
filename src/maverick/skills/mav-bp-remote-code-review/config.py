from maverick.models import SkillConfig
from maverick.names import MAV_BP_REMOTE_CODE_REVIEW

CONFIG = SkillConfig(
    name=MAV_BP_REMOTE_CODE_REVIEW,
    description=(
        "Mandatory remote code review on every pull request. Defines the contract for "
        "a GitHub Actions workflow that runs the agent-code-reviewer in CI when a PR "
        "is opened, synchronized, or reopened. Used as a dependency by do-issue-solo "
        "and do-epic to enforce the review gate, and by do-maverick-alignment to audit "
        "the workflow's presence."
    ),
    user_invocable=False,
    disable_model_invocation=True,
    depends_on=[],
    assets=["code-review.yml"],
)

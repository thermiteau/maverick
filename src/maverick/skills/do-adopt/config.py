from maverick.models import SkillConfig
from maverick.names import (
    DO_ADOPT,
    MAV_BP_LINTING,
    MAV_BP_TESTING,
    MAV_GIT_WORKFLOW,
    MAV_LOCAL_VERIFICATION,
)

CONFIG = SkillConfig(
    name=DO_ADOPT,
    description=(
        "Scan a project for missing best-practice areas and implement the top"
        " recommendation for each gap (linting, unit testing) — installs"
        " tools, writes configs, verifies, and commits. Pass 'recommend' to"
        " stop after writing recommendations without implementing (replaces"
        " the old do-recommend skill)."
    ),
    argument_hint="[recommend] [topic] (optional — omit for all topics; 'recommend' skips implementation)",
    user_invocable=True,
    # Runs in an isolated forked context: the audit/setup work is
    # self-contained and would otherwise pollute the caller's window
    # (the #106 premature-stop class). The body is the fork's prompt.
    context="fork",
    disable_model_invocation=False,
    depends_on=[
        MAV_BP_LINTING,
        MAV_BP_TESTING,
        MAV_GIT_WORKFLOW,
        MAV_LOCAL_VERIFICATION,
    ],
)

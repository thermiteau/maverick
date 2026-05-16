from maverick.models import SkillConfig
from maverick.names import MAV_GIT_WORKFLOW

CONFIG = SkillConfig(
    name=MAV_GIT_WORKFLOW,
    description=(
        "Git branching strategy, commit conventions, merge conflict handling, and branch lifecycle. Implements a simplified Gitflow with protected branches and conventional commits. Covers worktree-based multi-story workflows and cross-references stacked-PR handling."
    ),
    user_invocable=False,
    disable_model_invocation=True,
    depends_on=[],
)

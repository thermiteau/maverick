from maverick.models import SkillConfig
from maverick.names import MAV_GIT_WORKFLOW, MAV_STACKED_PRS

CONFIG = SkillConfig(
    name=MAV_STACKED_PRS,
    description=(
        "How to stack a PR on top of an unmerged sibling branch, and how to retarget"
        " it to the repo's default branch once the sibling merges. Prevents"
        " orphan-merge incidents when a dependent story is ready before its parent."
    ),
    user_invocable=False,
    disable_model_invocation=True,
    depends_on=[MAV_GIT_WORKFLOW],
)

from maverick.models import SkillConfig
from maverick.names import MAV_DURABILITY_ON_GH

CONFIG = SkillConfig(
    name=MAV_DURABILITY_ON_GH,
    description=(
        "Durability conventions for multi-instance Maverick workflows. Covers cold-start"
        " hydration from GitHub, marker-write protocols, push-per-task cadence, and"
        " recreating worktrees from remote branches. GitHub is the source of truth;"
        " local files are a cache."
    ),
    user_invocable=False,
    disable_model_invocation=False,
    depends_on=[],
)

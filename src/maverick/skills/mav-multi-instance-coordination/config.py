from maverick.models import SkillConfig
from maverick.names import (
    MAV_BLOCK_PROPAGATION,
    MAV_DURABILITY_ON_GH,
    MAV_MULTI_INSTANCE_COORDINATION,
)

CONFIG = SkillConfig(
    name=MAV_MULTI_INSTANCE_COORDINATION,
    description=(
        "Claim, lease, heartbeat, and release protocols for when multiple Claude Code"
        " instances may act on the same issue or epic concurrently. GitHub labels and"
        " marker comments are the coordination surface; local state is a cache."
    ),
    user_invocable=False,
    disable_model_invocation=False,
    depends_on=[MAV_DURABILITY_ON_GH, MAV_BLOCK_PROPAGATION],
)

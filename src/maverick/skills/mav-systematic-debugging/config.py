from maverick.models import SkillConfig
from maverick.names import MAV_SYSTEMATIC_DEBUGGING

CONFIG = SkillConfig(
    name=MAV_SYSTEMATIC_DEBUGGING,
    description=(
        "Use when encountering any bug, test failure, or unexpected behaviour during implementation. Requires root cause investigation before proposing fixes."
    ),
)

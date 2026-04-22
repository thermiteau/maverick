from maverick.models import SkillConfig
from maverick.names import (
    DO_RECOMMEND,
    MAV_BP_LINTING,
    MAV_BP_UNIT_TESTING,
)

CONFIG = SkillConfig(
    name=DO_RECOMMEND,
    description=(
        "Scan a project for missing best-practice areas and recommend 1-3"
        " technology options for each gap. Currently covers linting and"
        " unit testing. Writes recommendations to"
        " docs/maverick/recommendations/<topic>.md."
    ),
    argument_hint="topic to recommend (optional — processes all topics if omitted)",
    user_invocable=True,
    disable_model_invocation=False,
    depends_on=[
        MAV_BP_LINTING,
        MAV_BP_UNIT_TESTING,
    ],
)

from maverick.models import SkillConfig
from maverick.names import (
    DO_ADOPT,
    DO_RECOMMEND,
    MAV_BP_LINTING,
    MAV_BP_TESTING,
    MAV_GIT_WORKFLOW,
    MAV_LOCAL_VERIFICATION,
)

CONFIG = SkillConfig(
    name=DO_ADOPT,
    description=(
        "Scan a project for missing best-practice areas and implement the top"
        " recommendation for each gap. Currently covers linting and unit"
        " testing. Installs tools, writes configs, and adds CI steps."
    ),
    argument_hint="topic to adopt (optional — processes all topics if omitted)",
    user_invocable=True,
    disable_model_invocation=False,
    depends_on=[
        DO_RECOMMEND,
        MAV_BP_LINTING,
        MAV_BP_TESTING,
        MAV_GIT_WORKFLOW,
        MAV_LOCAL_VERIFICATION,
    ],
)

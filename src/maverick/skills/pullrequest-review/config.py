from maverick.models import SkillConfig
from maverick.names import PULLREQUEST_REVIEW

CONFIG = SkillConfig(
    name=PULLREQUEST_REVIEW,
    description=(
        "How to process code review feedback — verify before implementing, push back when wrong, clarify before acting on partial understanding. Applied when receiving review from the code-reviewer agent or human reviewers."
    ),
    user_invocable=False,
    disable_model_invocation=False,
    depends_on=[],
)

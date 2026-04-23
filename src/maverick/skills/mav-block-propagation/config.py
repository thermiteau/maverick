from maverick.models import SkillConfig
from maverick.names import MAV_BLOCK_PROPAGATION, MAV_DURABILITY_ON_GH

CONFIG = SkillConfig(
    name=MAV_BLOCK_PROPAGATION,
    description=(
        "Idempotent, resumable propagation of a `blocked-by:#N` block from an ejected"
        " story to every transitive downstream story in the epic DAG. Triggered when"
        " agent-code-reviewer ejects a PR for human handling."
    ),
    user_invocable=False,
    disable_model_invocation=False,
    depends_on=[MAV_DURABILITY_ON_GH],
)

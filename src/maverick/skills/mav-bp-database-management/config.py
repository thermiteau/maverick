from maverick.models import SkillConfig
from maverick.names import MAV_BP_DATABASE_MANAGEMENT

CONFIG = SkillConfig(
    name=MAV_BP_DATABASE_MANAGEMENT,
    description=(
        "Database and data management conventions for all projects using databases. Covers schema migrations, backup strategy, data lifecycle, index management, and connection pooling. Applied when designing, implementing, or reviewing database interactions."
    ),
    user_invocable=False,
    disable_model_invocation=True,
    depends_on=[],
)

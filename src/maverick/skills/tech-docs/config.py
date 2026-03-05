from maverick.models import SkillConfig
from maverick.names import TECH_DOCS

CONFIG = SkillConfig(
    name=TECH_DOCS,
    description=(
        "Create or update technical documentation for a project. Covers architecture, service interactions, data flows, and design decisions. Produces professional markdown with Mermaid diagrams."
    ),
    user_invocable=True,
    disable_model_invocation=False,
    depends_on=[],
)

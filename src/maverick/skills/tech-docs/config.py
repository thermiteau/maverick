from maverick.models import SkillConfig
from maverick.names import TECH_DOCS

CONFIG = SkillConfig(
    name=TECH_DOCS,
    description=(
        "Technical documentation standards — document structure, writing style,"
        " file organisation, mermaid diagrams, and validation."
        " Referenced by do-docs and tech-docs-writer."
    ),
    user_invocable=False,
    depends_on=[],
)

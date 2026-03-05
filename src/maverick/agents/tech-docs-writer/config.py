from maverick.models import AgentConfig
from maverick.names import AGENT_TECH_DOCS_WRITER, DO_DOCS, MAV_SCOPE_BOUNDARIES, TECH_DOCS

CONFIG = AgentConfig(
    name=AGENT_TECH_DOCS_WRITER,
    description=(
        "Autonomous technical documentation writer. Dispatched when documentation"
        " needs to be created or updated — architecture, services, data flows, design"
        " decisions, or technology choices. Produces professional markdown with Mermaid"
        " diagrams."
    ),
    model="sonnet",
    color="blue",
    skills=[
        DO_DOCS,
        TECH_DOCS,
        MAV_SCOPE_BOUNDARIES,
    ],
)

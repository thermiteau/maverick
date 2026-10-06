from maverick.models import AgentConfig, ClaudeAgentOptions
from maverick.names import AGENT_TECH_DOCS_WRITER, DO_DOCS, DO_TECH_DOCS, MAV_SCOPE_BOUNDARIES

CONFIG = AgentConfig(
    name=AGENT_TECH_DOCS_WRITER,
    description=(
        "Autonomous technical documentation writer. Dispatched when documentation"
        " needs to be created or updated — architecture, services, data flows, design"
        " decisions, or technology choices. Produces professional markdown with Mermaid"
        " diagrams."
    ),
    skills=[
        DO_DOCS,
        DO_TECH_DOCS,
        MAV_SCOPE_BOUNDARIES,
    ],
    claude=ClaudeAgentOptions(model="sonnet", color="blue"),
)

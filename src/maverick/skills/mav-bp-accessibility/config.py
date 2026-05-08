from maverick.models import SkillConfig
from maverick.names import MAV_BP_ACCESSIBILITY

CONFIG = SkillConfig(
    name=MAV_BP_ACCESSIBILITY,
    description=(
        "Accessibility conventions for projects with user-facing interfaces. Covers WCAG 2.1 AA compliance, semantic HTML, keyboard navigation, colour contrast, screen reader support, and automated a11y testing. Applied when building or reviewing user-facing web or mobile applications."
    ),
    user_invocable=False,
    disable_model_invocation=True,
    depends_on=[],
)

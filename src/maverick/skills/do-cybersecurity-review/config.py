from maverick.models import ClaudeSkillOptions, SkillConfig
from maverick.names import (
    DO_CYBERSECURITY_REVIEW,
    MAV_BP_APPLICATION_SECURITY,
    MAV_SCOPE_BOUNDARIES,
)

CONFIG = SkillConfig(
    name=DO_CYBERSECURITY_REVIEW,
    description=(
        "Audit a codebase for security risks in one of two modes. In full-audit "
        "mode it scans the entire codebase and writes a findings report to "
        "docs/security-audit.md (run as part of do-init or on demand). In update "
        "mode it hands a diff to the independent agent-security-reviewer, which "
        "reviews the diff plus the code it could impact in a fresh context and "
        "returns PASS, FINDINGS or BLOCKING. Applies the project's own security "
        "checklist from docs/maverick/skills/ and its invariant checks. Covers "
        "secrets exposure, dependency vulnerabilities, "
        "authentication and authorisation patterns, input validation, transport "
        "security, and common OWASP risks."
    ),
    user_invocable=True,
    # Runs in an isolated forked context: the audit/setup work is
    # self-contained and would otherwise pollute the caller's window
    # (the #106 premature-stop class). The body is the fork's prompt.
    claude=ClaudeSkillOptions(context="fork"),
    disable_model_invocation=False,
    depends_on=[MAV_BP_APPLICATION_SECURITY, MAV_SCOPE_BOUNDARIES],
)

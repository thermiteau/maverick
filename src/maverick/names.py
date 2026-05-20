"""Centralised skill and agent name constants for template generators."""

# ---------------------------------------------------------------------------
# Skills
# ---------------------------------------------------------------------------

DO_ADOPT = "do-adopt"
DO_CODE = "do-code"
DO_CYBERSECURITY_REVIEW = "do-cybersecurity-review"
DO_DOCS = "do-docs"
DO_EPIC = "do-epic"
DO_INIT = "do-init"
DO_INSTALL = "do-install"
DO_ISSUE_GUIDED = "do-issue-guided"
DO_ISSUE_SOLO = "do-issue-solo"
DO_MAVERICK_ALIGNMENT = "do-maverick-alignment"
DO_PULLREQUEST_REVIEW = "do-pullrequest-review"
DO_RECOMMEND = "do-recommend"
DO_TECH_DOCS = "do-tech-docs"
DO_TEST = "do-test"
DO_UPSKILL = "do-upskill"
MAV_BP_ACCESSIBILITY = "mav-bp-accessibility"
MAV_BP_ALERTING = "mav-bp-alerting"
MAV_BP_API_DESIGN = "mav-bp-api-design"
MAV_BP_APPLICATION_SECURITY = "mav-bp-application-security"
MAV_BP_CICD = "mav-bp-cicd"
MAV_BP_CICD_AZURE = "mav-bp-cicd-azure"
MAV_BP_CICD_BITBUCKET = "mav-bp-cicd-bitbucket"
MAV_BP_CICD_GITHUB = "mav-bp-cicd-github"
MAV_BP_CICD_GITLAB = "mav-bp-cicd-gitlab"
MAV_BP_CODE_REVIEW = "mav-bp-code-review"
MAV_BP_DATABASE_MANAGEMENT = "mav-bp-database-management"
MAV_BP_DEPENDENCY_MANAGEMENT = "mav-bp-dependency-management"
MAV_BP_DOCUMENTATION = "mav-bp-documentation"
MAV_BP_ENVIRONMENT_MANAGEMENT = "mav-bp-environment-management"
MAV_BP_ERROR_HANDLING = "mav-bp-error-handling"
MAV_BP_INFRASTRUCTURE_AS_CODE = "mav-bp-infrastructure-as-code"
MAV_BP_INTEGRATION_TESTING = "mav-bp-integration-testing"
MAV_BP_LINTING = "mav-bp-linting"
MAV_BP_LOGGING = "mav-bp-logging"
MAV_BP_OBSERVABILITY = "mav-bp-observability"
MAV_BP_REMOTE_CODE_REVIEW = "mav-bp-remote-code-review"
MAV_BP_SOLUTIONS_DESIGN = "mav-bp-solutions-design"
MAV_BP_SOURCE_CONTROL = "mav-bp-source-control"
MAV_BP_TASK_TRACKING = "mav-bp-task-tracking"
MAV_BP_UNIT_TESTING = "mav-bp-unit-testing"
MAV_BP_VERSIONING = "mav-bp-versioning"
MAV_BLOCK_PROPAGATION = "mav-block-propagation"
MAV_CLAUDE_CODE_RECOVERY = "mav-claude-code-recovery"
MAV_CREATE_SOLUTION_DESIGN = "mav-create-solution-design"
MAV_CREATE_TASKS = "mav-create-tasks"
MAV_DURABILITY_ON_GH = "mav-durability-on-gh"
MAV_GITHUB_ISSUE_WORKFLOW = "mav-github-issue-workflow"
MAV_GIT_WORKFLOW = "mav-git-workflow"
MAV_LOCAL_VERIFICATION = "mav-local-verification"
MAV_MULTI_INSTANCE_COORDINATION = "mav-multi-instance-coordination"
MAV_PLAN_EXECUTION = "mav-plan-execution"
MAV_SCOPE_BOUNDARIES = "mav-scope-boundaries"
MAV_STACKED_PRS = "mav-stacked-prs"
MAV_SYSTEMATIC_DEBUGGING = "mav-systematic-debugging"

ALL_SKILL_NAMES = {
    DO_ADOPT,
    DO_CODE,
    DO_CYBERSECURITY_REVIEW,
    DO_DOCS,
    DO_EPIC,
    DO_INIT,
    DO_INSTALL,
    DO_ISSUE_GUIDED,
    DO_ISSUE_SOLO,
    DO_MAVERICK_ALIGNMENT,
    DO_PULLREQUEST_REVIEW,
    DO_RECOMMEND,
    DO_TECH_DOCS,
    DO_TEST,
    DO_UPSKILL,
    MAV_BP_ACCESSIBILITY,
    MAV_BP_ALERTING,
    MAV_BP_API_DESIGN,
    MAV_BP_APPLICATION_SECURITY,
    MAV_BP_CICD,
    MAV_BP_CICD_AZURE,
    MAV_BP_CICD_BITBUCKET,
    MAV_BP_CICD_GITHUB,
    MAV_BP_CICD_GITLAB,
    MAV_BP_CODE_REVIEW,
    MAV_BP_DATABASE_MANAGEMENT,
    MAV_BP_DEPENDENCY_MANAGEMENT,
    MAV_BP_DOCUMENTATION,
    MAV_BP_ENVIRONMENT_MANAGEMENT,
    MAV_BP_ERROR_HANDLING,
    MAV_BP_INFRASTRUCTURE_AS_CODE,
    MAV_BP_INTEGRATION_TESTING,
    MAV_BP_LINTING,
    MAV_BP_LOGGING,
    MAV_BP_OBSERVABILITY,
    MAV_BP_REMOTE_CODE_REVIEW,
    MAV_BP_SOLUTIONS_DESIGN,
    MAV_BP_SOURCE_CONTROL,
    MAV_BP_TASK_TRACKING,
    MAV_BP_UNIT_TESTING,
    MAV_BP_VERSIONING,
    MAV_BLOCK_PROPAGATION,
    MAV_CLAUDE_CODE_RECOVERY,
    MAV_CREATE_SOLUTION_DESIGN,
    MAV_CREATE_TASKS,
    MAV_DURABILITY_ON_GH,
    MAV_GITHUB_ISSUE_WORKFLOW,
    MAV_GIT_WORKFLOW,
    MAV_LOCAL_VERIFICATION,
    MAV_MULTI_INSTANCE_COORDINATION,
    MAV_PLAN_EXECUTION,
    MAV_SCOPE_BOUNDARIES,
    MAV_STACKED_PRS,
    MAV_SYSTEMATIC_DEBUGGING,
}

# ---------------------------------------------------------------------------
# Agents
# ---------------------------------------------------------------------------

AGENT_CODE_REVIEWER = "agent-code-reviewer"
AGENT_ISSUE_ANALYST = "agent-issue-analyst"
AGENT_GITHUB_ISSUE_PLANNER = "agent-github-issue-planner"
AGENT_MAVERICK = "agent-maverick"
AGENT_TECH_DOCS_WRITER = "agent-tech-docs-writer"
AGENT_SESSION_REVIEWER = "agent-session-reviewer"

ALL_AGENT_NAMES = {
    AGENT_CODE_REVIEWER,
    AGENT_ISSUE_ANALYST,
    AGENT_GITHUB_ISSUE_PLANNER,
    AGENT_MAVERICK,
    AGENT_TECH_DOCS_WRITER,
    AGENT_SESSION_REVIEWER,
}

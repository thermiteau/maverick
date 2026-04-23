from maverick.models import SkillConfig
from maverick.names import (
    DO_EPIC,
    DO_ISSUE_SOLO,
    MAV_BLOCK_PROPAGATION,
    MAV_BP_CICD,
    MAV_CLAUDE_CODE_RECOVERY,
    MAV_CREATE_SOLUTION_DESIGN,
    MAV_CREATE_TASKS,
    MAV_DURABILITY_ON_GH,
    MAV_GIT_WORKFLOW,
    MAV_GITHUB_ISSUE_WORKFLOW,
    MAV_LOCAL_VERIFICATION,
    MAV_MULTI_INSTANCE_COORDINATION,
    MAV_PLAN_EXECUTION,
    MAV_SCOPE_BOUNDARIES,
    MAV_STACKED_PRS,
)

CONFIG = SkillConfig(
    name=DO_EPIC,
    description=(
        "Work on a multi-story GitHub epic end-to-end. Builds a DAG from the child"
        " stories, groups them into waves, runs waves in parallel via per-story"
        " worktrees, ejects PRs that fail agent-code-review for human handling, and"
        " propagates blocks to downstream stories. Requires git worktrees."
    ),
    argument_hint="epic issue number (e.g., 123)",
    user_invocable=True,
    disable_model_invocation=False,
    depends_on=[
        MAV_SCOPE_BOUNDARIES,
        MAV_MULTI_INSTANCE_COORDINATION,
        MAV_DURABILITY_ON_GH,
        MAV_BLOCK_PROPAGATION,
        MAV_GIT_WORKFLOW,
        MAV_STACKED_PRS,
        MAV_GITHUB_ISSUE_WORKFLOW,
        MAV_CREATE_SOLUTION_DESIGN,
        MAV_CREATE_TASKS,
        MAV_PLAN_EXECUTION,
        MAV_LOCAL_VERIFICATION,
        MAV_BP_CICD,
        MAV_CLAUDE_CODE_RECOVERY,
        DO_ISSUE_SOLO,
    ],
)

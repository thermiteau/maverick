**Auto-merge to `develop` without human eyes.** The new workflow merges any PR the agent code-reviewer approves. The eject path is the only protection. If the reviewer is too lenient, low-quality code lands. Mitigation: invest heavily in agent-code-reviewer quality (WP8); make ejection cheap and frequent rather than rare; consider a "shadow reviewer" mode where two independent reviewer agents must agree before approval lands during a trust-building period.

**Push-per-task increases CI load.** Each task triggers a CI run. For a 10-task story that's 10 CI runs. Mitigation: configure CI to skip drafts or use path-scoped triggers; measure cost on a representative epic before defaulting on.

**Worktree disk usage.** A wide wave (10 stories in parallel) means 10 worktrees checked out. Disk, IDE indexing, and any per-checkout caches multiply. Mitigation: worktree cleanup must be reliable on every exit path (success, eject, crash); consider a max-concurrent-worktrees cap.

**`maverick-bot` security.** A separate GitHub identity with merge rights is a juicy target. Mitigation: scope tokens minimally (only the repos in scope); rotate regularly; audit `maverick-bot` actions weekly.

**Race conditions in claim.** GitHub's API is not strongly consistent. Two instances claiming the same issue at the same millisecond can both succeed at the label-write step. Mitigation: read-after-write at CC4; if both instances see each other's claim afterward, one (deterministically — e.g. lower instance-id wins) backs off and releases. Document explicitly in WP2.

**Migration path.** Existing in-flight epics will not have `maverick-dag` or `maverick-state` comments. Mitigation: COLD step gracefully handles missing markers by treating the run as a fresh start at whatever phase the issue happens to be in; document a manual "convert this in-flight epic to the new workflow" recipe.

**Backwards compatibility for the "no-worktree" world.** Some users (or some projects) may not be able to enable worktrees. Mitigation: keep `do-issue-solo` viable in non-worktree mode for single-issue work; `do-epic` requires worktrees unconditionally because parallelism without isolation is unsafe.

**Open question — tasks vs sub-issues at story level.** `mav-create-tasks` already splits into checklist (< 5 tasks) or sub-issues (≥ 5). With push-per-task, the sub-issue path becomes more attractive (each sub-issue is a durable atomic unit). Worth revisiting the threshold and the per-task durability story.

**Open question — `do-task-solo` (no GH) compatibility.** The new workflow assumes GitHub as the coordination substrate. `do-task-solo` operates without GH issues. Either: (a) `do-task-solo` is exempt from multi-instance coordination (single-user assumption), or (b) it's deprecated in favour of always creating a GH issue. Needs a decision.

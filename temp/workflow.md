```mermaid
flowchart TD
    %% ─────────────── Request intake ───────────────
    A[Human makes request]

    B[Written to Claude Code CLI]
    C[Written to GitHub Issue]

    A --> B
    A --> C

    %% ─────────────── Preconditions ───────────────
    B --> PRE
    C --> PRE
    PRE{Git worktrees enabled<br/>and supported in this checkout?}
    PRE -- No --> PREF[Abort with hard failure.<br/>Worktrees are a required capability —<br/>workflow cannot run without them]
    PREF --> P
    PRE -- Yes --> COLD

    %% ─────────────── Cold-start recovery ───────────────
    COLD[**Cold-start recovery — assume local state is empty/stale.**<br/>For the requested target, hydrate local state from GH:<br/>• read DAG from epic's pinned `maverick-dag` JSON comment<br/>• read latest epic-state snapshot from rolling `maverick-state` comment<br/>• read claim/block/lease labels and comments<br/>• read open PRs, branches, and CI status<br/>If a `maverick-bprop:#N` propagation marker exists, **resume** it before continuing.<br/>GH is source of truth — local files are a derivable cache]
    COLD --> CC1

    %% ─────────────── Multi-instance coordination ───────────────
    CC1[Resolve target — issue, group of issues, or epic.<br/>Look up on GH:<br/>• claim state via `claude-in-progress` label, assignee, lease comments<br/>• block state via `blocked-by:#N` label on target + parent epic + siblings]

    CC1 --> CC0{Target carries a<br/>`blocked-by:#N` label?}
    CC0 -- Yes --> CC0A[Abort cleanly.<br/>Report to user: 'blocked by ejected #N — needs human resolution'.<br/>Do not claim, do not modify the issue]
    CC0A --> P
    CC0 -- No --> CC2

    CC2{Already claimed by another<br/>Claude Code instance?}

    CC2 -- Yes — lease still valid --> CC2A[Abort cleanly.<br/>Report to user: 'in progress by instance &lt;id&gt; until &lt;expiry&gt;'.<br/>Do not modify the issue]
    CC2A --> P

    CC2 -- Yes — lease stale<br/>(holder likely crashed) --> CC2B[Decide: take over or defer.<br/>If taking over: post takeover comment naming prior instance,<br/>then continue to claim]

    CC2 -- No --> CC3
    CC2B --> CC3

    CC3{Decide claim scope}
    CC3 -- Whole epic --> CC3A[Scope = epic issue + every child story]
    CC3 -- Group of stories --> CC3B[Scope = selected stories<br/>typically one wave from the epic DAG]
    CC3 -- Single story --> CC3C[Scope = this story only]

    CC3A --> CC4
    CC3B --> CC4
    CC3C --> CC4

    CC4[Atomic claim — for each issue in scope, in one transaction:<br/>• add label `claude-in-progress`<br/>• assign `maverick-bot` with instance-id in comment<br/>• post lease comment: instance-id, host, scope-list, lease-expiry timestamp<br/>Re-read after write to detect simultaneous-claim races — loser aborts]

    CC4 --> CC5[Start lease heartbeat — refresh expiry on each claimed issue<br/>at a short interval (e.g. every 1–2 min)<br/>with short lease TTL (e.g. 5–10 min)<br/>so machine death is detected quickly via stale lease]

    CC5 --> D

    %% ─────────────── Pre-development ───────────────
    D[Evaluated by Claude Code]

    E{Is understood/complete?}
    F{Is source GH?}

    G[Write response to GitHub request issue]
    H[Ask clarifying questions until enough is known to update the GH request issue with clarity]

    I[mav-create-solution-design]
    J[Update Request with Design]
    K[mav-create-tasks]

    L{Should this be an epic or a story?}

    M[Create Epic as GH Issue]
    N[Create multiple stories as GH Issues]

    O[Create 1 Story as GH Issue]

    P([END])

    D --> E
    E -- Yes --> I
    E -- No --> F
    F -- Yes --> G
    G --> RC0[Release claim before exit]
    RC0 --> P
    F -- No --> H
    H --> D
    I --> J
    J --> K
    K --> L
    L -- Yes --> M
    M --> N
    L -- No --> O

    %% ─────────────── Epic planning (DAG + waves) ───────────────
    N --> EP1[Analyse cross-story dependencies<br/>and shared-file collisions<br/>build a DAG.<br/>**Persist full DAG to GH** as machine-readable JSON<br/>in a pinned `maverick-dag` comment on the epic issue<br/>(durable across machine deaths — any instance reads this)]
    EP1 --> EP2[Group stories into execution waves<br/>siblings with no shared deps share a wave]
    EP2 --> EP3[Record waves + ordering<br/>in epic task-table comment<br/>(human-readable form, complements the DAG JSON)]
    EP3 --> EP4[Initialise epic-state file `.claude/epic-state.json`<br/>tracks merged / in-flight / blocked.<br/>**Mirror to GH** as a rolling `maverick-state` JSON comment<br/>on the epic issue — refreshed on every state transition]
    EP4 --> EP5[If claim scope = whole epic,<br/>extend claim to cover any newly-created child stories]
    EP5 --> Q1([END of pre-development — epic])

    O --> Q2([END of pre-development — story])

    %% ─────────────── Development — wave selection ───────────────
    Q1 --> WS[Read epic-state, select next wave<br/>limited to issues inside current claim scope.<br/>**Exclude any story carrying a `blocked-by:#N` label** —<br/>re-check label state at selection time so a human-resolved<br/>ejection automatically unblocks downstream work]
    WS --> WBLK{Wave still has any unblocked stories?}
    WBLK -- No, fully blocked --> WSKIP[Skip this wave — log blocker.<br/>If all remaining waves are blocked, halt epic processing<br/>and report blockers to user]
    WSKIP --> AO
    WBLK -- Yes --> WTC[For each unblocked story in wave,<br/>create a git worktree off develop]
    WTC --> PD{Parallel subagents allowed?<br/>• user policy permits subagents<br/>• capacity available}

    PD -- Yes --> PAR[Dispatch one subagent per worktree<br/>per-story flow runs concurrently<br/>main session aggregates results]
    PD -- No --> SER[Process worktrees one at a time<br/>per-story flow runs serially]

    Q2 --> SOLOWT[Create a single worktree off develop]
    SOLOWT --> R

    PAR --> R
    SER --> R

    %% ─────────────── Per-story flow ───────────────
    R[Pick story to work on]

    R --> RV{Re-verify claim on this story still held<br/>by this instance and lease not expired?<br/>**AND** no `blocked-by:#N` label on the issue?<br/>(handles late propagation from a sibling ejection)}
    RV -- No, claim lost or now blocked --> RVA[Abort this story.<br/>If blocked: do NOT push or comment.<br/>If claim lost: release worktree, log loss reason]
    RVA --> AO

    RV -- Yes --> SC{Depends on a sibling story whose<br/>PR is open but not yet merged?}
    SC -- Yes --> SK[Branch from the sibling branch<br/>stacked PR — set base = sibling branch<br/>per mav-stacked-prs]
    SC -- No --> SB[Branch from develop<br/>per mav-git-workflow]

    SK --> T
    SB --> T

    T[Read next task from checklist or sub-issue]
    T --> U[Implement the change]
    U --> V[Run local verification<br/>lint / typecheck / tests<br/>per mav-local-verification]
    V --> W{Checks pass?}
    W -- No --> X[Diagnose root cause<br/>per mav-systematic-debugging]
    X --> U
    W -- Yes --> Y[Conventional commit referencing issue<br/>**then push immediately to remote** — durability checkpoint per task.<br/>If branch not yet on remote, this is the first push.<br/>Pre-push hook still runs but at single-task scope, not full-story scope]
    Y --> Z[Update tasks comment or close sub-issue<br/>(also durable on GH — survives machine death)]
    Z --> AA{More tasks remaining?}
    AA -- Yes --> T
    AA -- No --> AB[Run full verification suite]

    %% ─────────────── Docs, push, CI ───────────────
    AB --> AF{Documentation impacted?}
    AF -- Yes --> AG[Dispatch agent-tech-docs-writer<br/>update mode<br/>commit doc updates to branch]
    AG --> AH[Pre-push verification]
    AF -- No --> AH

    %% Stacked-PR retarget guard
    AH --> SR{Stacked branch?<br/>git merge-base check —<br/>is sibling base now fully in develop?}
    SR -- Yes, base merged --> RT[Retarget PR base to develop<br/>per mav-stacked-prs<br/>prevents orphan-merge incidents]
    SR -- No, still depends on sibling --> AI
    RT --> AI[Push branch to remote]

    AI --> AJ[Monitor CI per mav-bp-cicd]
    AJ --> AK{CI passes?}
    AK -- No --> AL[Read failure logs, fix locally]
    AL --> AH

    AK -- Yes --> AND[Open PR ready-for-review<br/>base = develop or sibling branch<br/>title + body from issue]

    %% ─────────────── Code review — binary outcome ───────────────
    AND --> ACX[**HARD GATE** — Dispatch agent-code-reviewer<br/>against the PR<br/>Stage 1: spec compliance<br/>Stage 2: code quality]
    ACX --> AD{Review approved?}

    %% ─── Eject path: review found issues ───
    AD -- No, issues found --> AEJ[Eject PR for human handling:<br/>• post review summary as PR comment<br/>• request human review on the PR<br/>• apply label `needs-human` to issue and PR<br/>• do NOT attempt to auto-fix]
    AEJ --> AEJR[Release claim on this story<br/>human now owns this PR end-to-end]
    AEJR --> ECJ{Story belongs to an epic?}
    ECJ -- No --> AO

    ECJ -- Yes --> USJ[Update epic-state — this story EJECTED.<br/>Refresh `maverick-state` comment on the epic issue]
    USJ --> BMARK[**Write propagation marker** on the epic issue:<br/>`maverick-bprop:#&lt;ejected-issue&gt;` JSON comment<br/>listing all transitive descendants from the DAG that need blocking.<br/>Marker means: 'block walk in progress — resume if you find this']
    BMARK --> BPROP[**Propagate block to ALL transitive downstream stories** — idempotent.<br/>Walk the DAG from the ejected story to every dependent descendant.<br/>For each (skip those already labelled — safe to re-run):<br/>• apply label `blocked-by:#&lt;ejected-issue&gt;` on GH<br/>• post block comment naming the ejected PR/issue<br/>• update epic-state and refresh `maverick-state` comment]
    BPROP --> BCLEAR[Clear `maverick-bprop:#N` propagation marker<br/>once every descendant is labelled — propagation complete]
    BCLEAR --> BCANCEL[Cancel any in-flight subagents whose story<br/>is now in the blocked set —<br/>release their claims, do NOT push their work]
    BCANCEL --> WW

    %% ─── Approved path: auto-merge ───
    AD -- Yes, no issues --> APV[maverick-bot posts<br/>`gh pr review --approve`<br/>with verdict + timestamp + instance-id —<br/>creates auditable agent-reviewed trail]
    APV --> AMERGE[Auto-merge PR<br/>`gh pr merge --auto --squash`<br/>or merge directly once CI is green]
    AMERGE --> AM[Post completion comment on issue<br/>including code-review verdict + timestamp + instance-id<br/>per mav-github-issue-workflow]

    %% ─────────────── Per-story claim release ───────────────
    AM --> RC1[Release claim on this story:<br/>• remove `claude-in-progress` label<br/>• post lease-released comment with instance-id<br/>• unassign]
    RC1 --> EC{Story belongs to an epic?}

    EC -- No --> AO

    EC -- Yes --> US[Update epic-state — story MERGED.<br/>Refresh `maverick-state` JSON comment on the epic issue<br/>so any instance can read current truth from GH]
    US --> WW{All stories in this wave resolved?<br/>each is either MERGED or EJECTED}
    WW -- No --> R
    WW -- Yes --> WMORE{More waves remain?<br/>and not blocked by EJECTED stories?}
    WMORE -- Yes --> WS
    WMORE -- No --> AO

    %% ─────────────── End-of-run claim cleanup ───────────────
    AO[Release any claims still held<br/>e.g. epic-level claim once all waves complete<br/>stop heartbeat]
    AO --> AOEND([END of development])
```

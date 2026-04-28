# GitHub Labels and Marker Comments

Maverick coordinates multi-instance workflows through labels and machine-readable comments on GitHub. This document is the canonical reference for those primitives. All skills, agents, and CLI helpers that touch workflow state must conform to what is described here.

## Design principles

1. **GitHub is the source of truth.** Local files are derivable caches.
   Any state another Maverick instance might need to resume a workflow
   must land on GitHub before the owning instance moves on.
2. **Machine-readable without being fragile.** Payloads are JSON inside
   language-tagged fenced code blocks so `grep`, GitHub search, and
   stable regex parsers all work.
3. **Idempotent.** Every write re-checks state so repeated writes do not
   corrupt or duplicate.
4. **Uniform across repos.** Every Maverick-managed repo uses the same
   label and marker names. Do not fork or rename per project.

## Labels

| Label                | Applied to | Meaning                                       | Who applies                                  |
| -------------------- | ---------- | --------------------------------------------- | -------------------------------------------- |
| `claude-in-progress` | issue      | A Claude Code instance has claimed this issue | Claude Code instance (on claim)              |
| `needs-human`        | issue + PR | Code reviewer ejected this for human handling | Claude Code instance (on eject)              |
| `blocked-by:#N`      | issue      | Depends transitively on ejected issue `#N`    | Claude Code instance (via block propagation) |

Labels must be created once per repo. Maverick's `do-init` can create them automatically when present.

### Label lifecycle

```
claim    → claude-in-progress added
release  → claude-in-progress removed
eject    → needs-human added (stays until human closes the issue)
block    → blocked-by:#N added
unblock  → blocked-by:#N removed (human only — Maverick never removes)
```

## Marker comments

All state markers are fenced JSON code blocks with a kind-specific language tag. The Markdown fence lets GitHub render them as code; the language tag lets parsers find them.

General shape:

````text
[optional preamble markdown]

```maverick-<kind>
{
  "…": "…"
}
````

````

### Marker kinds

| Kind | Lives on | Cardinality | Purpose |
| --- | --- | --- | --- |
| `maverick-dag` | Epic issue | One | Machine-readable DAG — stories, deps, shared files |
| `maverick-state` | Epic issue | One rolling | Current epic state snapshot |
| `maverick-claim` | Each claimed issue | One per active claim | Identifies the claiming instance |
| `maverick-lease` | Each claimed issue | One rolling | Heartbeat timestamp |
| `maverick-bprop` | Epic issue | One (transient) | Block-propagation in-flight; absent when propagation is complete |

"One rolling" means the single latest comment of that kind is authoritative; older ones are historical noise. Use the upsert pattern (update-in-place if the kind exists; otherwise post) — see `mav-durability-on-gh`.

### Payload shapes

**`maverick-dag`**
```json
{
  "epic": 123,
  "stories": {
    "140": {"deps": [], "files": ["app/src/boot.ts"]},
    "142": {"deps": ["140"], "files": ["app/src/admin/guard.ts"]}
  }
}
````

**`maverick-state`**

```json
{
  "epic": 123,
  "stories": {
    "140": "merged",
    "142": "in_flight",
    "143": "blocked",
    "150": "ejected"
  },
  "updated_at": "2026-04-23T10:15:00Z"
}
```

Valid status values: `pending`, `in_flight`, `merged`, `ejected`, `blocked`.

**`maverick-claim`**

```json
{
  "instance_id": "abc123",
  "host": "dev-laptop-01",
  "scope": ["140", "142", "143"],
  "claimed_at": "2026-04-23T10:10:00Z"
}
```

**`maverick-lease`**

```json
{
  "instance_id": "abc123",
  "expires_at": "2026-04-23T10:20:00Z",
  "heartbeat_at": "2026-04-23T10:18:00Z"
}
```

`expires_at` should be 10 minutes ahead of the latest heartbeat. Heartbeats
refresh every ~2 minutes.

**`maverick-bprop`**

```json
{
  "ejected": "142",
  "descendants": ["150", "160", "161"],
  "labelled": [],
  "started_at": "2026-04-23T10:20:00Z"
}
```

Once every descendant appears in `labelled`, delete the comment.

## Parser contract

Every Maverick CLI helper and skill uses the same parser
(`src/maverick/gh_state.py`). The contract:

- Marker fence is ` ```maverick-<kind> ` on a line by itself, followed by
  JSON, followed by a closing ` ``` ` on a line by itself.
- Only the first marker of a given kind in a comment body is parsed.
- Comments without a recognised marker kind are ignored.
- Whitespace inside the fence is tolerated but the tag line is literal.

Anything that deviates from this will not be read by other instances.
Don't hand-edit these comments unless you also respect the format.

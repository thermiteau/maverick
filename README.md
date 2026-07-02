<!-- PROJECT LOGO -->
<br />
<div align="center">
  <a href="https://github.com/thermiteau/maverick">
    <img src="docs/media/maverick-logo.png" alt="Maverick Logo" width="200" height="200">
  </a>

  <h1 align="center">Maverick</h1>

  <p align="center">
    Claude Code tooling to build software right
    <br />
    <a href="docs/overview.md"><strong>Explore the docs</strong></a>
    <br />
    <br />
    &middot;
    <a href="https://github.com/thermiteau/maverick/issues/new?labels=bug&template=bug-report.md">Report Bug</a>
    &middot;
    <a href="https://github.com/thermiteau/maverick/issues/new?labels=enhancement&template=feature-request.md">Request Feature</a>
  </p>
</div>

Maverick is a Claude Code ( Cursor and Codex ) plugin and local CLI commands that enables autonomous AI-driven software development while enforcing quality, security, and operational best practices.

It provides skills, agents, and hooks that constrain and guide LLM behaviour - making unattended development safe and reliable.

## The Problem Maverick Solves

LLMs generate code fast but don't come with any concept of quality, best practice or constraint. Claude Code will happily agree to build the world's worst idea, with a smile, because without guardrails:

- **No operational awareness** - LLMs don't add structured logging, alerting, or monitoring unless explicitly told to. Production code becomes undiagnosable.
- **No security reasoning** - LLMs reproduce vulnerable patterns from training data. SQL injection, XSS, and secrets exposure go unnoticed. It won't make any effort to ensure cybersecurity is maintained.
- **No testing discipline** - LLMs write working code and you can think you've got a product. Until it runs anywhere except on your machine, because it's filled with bugs you can't see. Without tests, those bugs ship.
- **No workflow discipline** - LLMs commit to main, skip CI, ignore conventions, and produce untraceable changes. If you ask an LLM to create a large amount of changes in a single attempt it will try, and you'll regret it.
- **No self-review** - LLMs don't question their own output. Code that looks correct may miss requirements or violate project conventions.

These risks multiply enormously in unattended development when no human is watching the LLM work. There is no developer catching issues in real-time, no reviewer glancing at the diff, no operator noticing silent failures. Every quality gap becomes a production risk.

## How Maverick Solves It

Maverick is comprised of four parts:

### Claude Code Plugin: Best practice

Maverick comes with Claude Code skills that defines how to write quality code. These are not detailed technical skills, they are the why and how of software development practices. These skills are part of the plugin and get loaded into Claude Code.

There are also a few technical skills that are so common, they have been predefined in the plugin.

### Claude Code Plugin: Mechanical enforcement

Safety rules are not prose the model can forget — the plugin ships hooks
that enforce them at the tool-call boundary:

- A **scope-guard hook** gates destructive git operations, commits and
  pushes on protected branches, infrastructure edits, and
  production-pattern commands. In interactive sessions rule hits ask you;
  in autonomous runs they are denied outright. Production patterns are
  denied in every mode.
- Infrastructure changes in autonomous runs require **verified
  issue-level authorization** (`maverick coord authorize`) — an agent
  cannot self-grant a scope the issue never approved.
- A **pre-merge auth scan** blocks auto-merging any PR that touches
  authentication surfaces or CI workflow definitions, regardless of the
  review verdict.
- A **SessionEnd hook** releases coordination claims on every exit path,
  and lease expiry covers machine death.

### Claude Code Plugin: Skills creation

Because every codebase is unique, there is no way to ship defined skills that are needed to enable Claude Code. So Maverick builds them when it is initialised in a project.

- First it looks to see if you have them already, and uses yours if they are there.
- If it cant find any, it reads your codebase and builds technical skills that match your tech stack and align with its best practice skills
- These become part of your code and you can change them as required

### Infrastructure as Code solution for remote Claude Code instances

There are multiple ways to run Claude Code, the most obvious being the software running locally on your machine.  This works well for interactive development where you ask Claude Code to complete a task, answer any questions as they come up and monitor the progress.

It falls down when you need to complete multiple features or bug fixes at the same time. Claude Code on local machines, doesnt scale.

Maverick solves this by deploying Claude Code workers to remote Claude platforms such as Amazon Web Services. Those workers are triggered by creating tickets (issues) in GitHub. The worker will autonomously complete the requirements and keep you up to date with notes in the Github Issue.

For most teams there is a simpler on-ramp first: a ready-made GitHub
Actions workflow (`templates/github/claude-maverick.yml`) runs Maverick
on GitHub-hosted runners — respond to `@claude` mentions, or label an
issue `claude-do` and `do-issue-solo` works it end-to-end. See the
remote-execution decision matrix in
[docs/claude-code-workers.md](docs/claude-code-workers.md) for choosing
between the GitHub Action, Claude cloud routines, and the self-hosted
EC2 pipeline. None of this is required — the plugin works on your local
machine and you can ask Claude to complete tasks solo or with
assistance.

## NOTE: This project is still in Alpha and under rapid change

I use this repo to build my own software and I aim to improve it every day. That means the change rate is pretty high until I get it to v1 release.

- The plugin skills, agents, and hooks are solid, and the full
  `do-issue-solo` pipeline is exercised end-to-end against real
  repositories.
- The `maverick` CLI carries the workflow's deterministic core
  (coordination, state, gates, reporting) with an extensive unit-test
  suite; the AWS worker pipeline is in maintenance mode in favour of the
  GitHub Action on-ramp for most use cases.

## Install

### Plugin

```sh
# Install the plugin (registers in ~/.claude/settings.json)
claude plugin marketplace add https://github.com/thermiteau/maverick
claude plugin install maverick@thermite
```

### CLI

This makes the `maverick` command available globally.

#### Prerequisites

- Python 3.10+
- [uv](https://docs.astral.sh/uv/) — Python package manager
- [Claude Code](https://docs.anthropic.com/en/docs/claude-code) — Anthropic's CLI for Claude
- Claude Code API Key

```sh
# Install system-wide from the repo
uv tool install .

# Or install in development mode
uv tool install -e .
```

## Usage

### Initialising an existing project (repo)

run `/maverick:do-init` within Claude Code

### Work on GitHub issues

With the plugin loaded, use skills directly in Claude Code:

```sh
/maverick:do-issue-solo 42
# Autonomous mode — Claude works end-to-end, only pausing when blocked

/maverick:do-issue-guided 42
# Guided mode — Claude pauses for approval at design and plan phases

/maverick:do-maverick-alignment
# Audit a codebase against Maverick standards

/maverick:do-adopt recommend
# Recommend (or, without 'recommend', implement) missing best practices

/maverick:do-upskill logging
# Generate a project-specific implementation skill for one topic
```

Or skip the terminal entirely: copy
`templates/github/claude-maverick.yml` into `.github/workflows/`, then
label any issue `claude-do` and Maverick completes it on a GitHub-hosted
runner — design, tasks, implementation, docs and security gates, PR,
review, and merge.

## Development

```sh
# Run unit tests
uv sync --extra test && uv run pytest tests/unit/ -v
```

CI runs automatically on pushes and PRs to `main` via GitHub Actions.

## License

Apache License 2.0

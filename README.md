<!-- PROJECT LOGO -->
<br />
<div align="center">
  <a href="https://github.com/othneildrew/Best-README-Template">
    <img src="docs/media/maverick-logo.png" alt="Logo" width="200" height="200">
  </a>

  <h1 align="center">Maverick</h1>

  <p align="center">
    Claude Code tooling to build software right
    <br />
    <a href="https://github.com/thermiteau/maverick/docs.overview.md"><strong>Explore the docs</strong></a>
    <br />
    <br />
    &middot;
    <a href="https://github.com/thermiteau/maverickissues/new?labels=bug&template=bug-report.md">Report Bug</a>
    &middot;
    <a href="hhttps://github.com/thermiteau/maverickissues/new?labels=enhancement&template=feature-request.md">Request Feature</a>
  </p>
</div>

Maverick is a Claude Code ( Cursor and Codex ) plugin and local CLI commands that enables autonomous AI-driven software development while enforcing quality, security, and operational best practices.

It provides skills, agents, and hooks that constrain and guide LLM behaviour - making unattended development safe and reliable.

## The Problem Maverick Solves

LLMs generate code fast but dont come with any concept of quality, best practice or constraint. Claude Code will happily agree to build the worlds worst idea, with a smile, because without guardrails:

- **No operational awareness** - LLMs don't add structured logging, alerting, or monitoring unless explicitly told to. Production code becomes undiagnosable.
- **No security reasoning** - LLMs reproduce vulnerable patterns from training data. SQL injection, XSS, and secrets exposure go unnoticed. It wont make any effort to ensure cybersecurity is maintined.
- **No testing discipline** - LLMs write working code and you can think youve got a product. Until it runs anywhere except on your machine because its filled with bugs you cant see. Without tests, those bugs ship.
- **No workflow discipline** - LLMs commit to main, skip CI, ignore conventions, and produce untraceable changes. If you ask an LLM to create a large ammount of changes ina single attempt it will try and you'll regret it.
- **No self-review** - LLMs don't question their own output. Code that looks correct may miss requirements or violate project conventions.

These risks multiply enourmously in unattended development when no human is watching the LLM work. There is no developer catching issues in real-time, no reviewer glancing at the diff, no operator noticing silent failures. Every quality gap becomes a production risk.

## How Maverick Solves It

Maverick is comprised of three parts:

### Claude Code Plugin: Best practice

Maverick comes with Claude Code skills that defines how to write quality code. These are not detailed technical skills, they are the why and how of software development practices. These skills are part of the plugin and get loaded into Claude Code.

There are also a few technical skills that are so common, they have been predefined in the plugin.

### Claude Code Plugin: Skills creation

Because every codebase is unique, there is no way to ship defined skills that are needed to enable Claude Code. So Maverick builds them when it is initialised in a project.

- First it looks to see if you have them already, and uses yours if they are there.
- If it cant find any, it reads your codebase and builds technical skills that match your tech stack and align with its best practice skills
- These become part of your code and you can change them as required

### Infrastructure as Code solution for remote Claude Code instances

There are multiple ways to run Claude Code, the most obvious being the software running locally on your machine.  This works well for interactive development where you ask Claude Code to complete a task, answer any questions as they come up and monitor the progress.

It falls down when you need to complete multiple features or bug fixes at the same time. Claude Code on local machines, doesnt scale.

Maverick solves this by deploying Claude Code workers to remote Claude platforms such as Amazon Web Services. Those workers are triggered by creating tickets (issues) in GitHub. The worker will autonomously complete the requirements and keep you up to date with notes in the Github Issue.

This is more complicated than cassual users may need and its not required to use Maverick. You can just use the plugin on your local machine and either ask Claude to complete a task solo or with assistance.

## NOTE: Thiis project is still in Alpha and under rapid change

I use this repo to build my own software and I aim to improve it every day. That means the change rate is pretty high until I get it to v1 release.

- The Claude plugin skills and agents are solid and work well.
- The CLI tools and Cloud infra deploy are still brittle and need a lot of work. Thats my next issue to fix/build.

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

run `/maverick:init` within Claude CLI

### Work on GitHub issues

With the plugin loaded, use skills directly in Claude Code:

```sh
/maverick:do-issue-solo 42
# Autonomous mode — Claude works end-to-end, only pausing when blocked

/maverick:do-issue-guided 42
# Guided mode — Claude pauses for approval at design and plan phases

/maverick:codebase-audit
# Audit a codebase against Maverick standards
```

## License

Apache License 2.0

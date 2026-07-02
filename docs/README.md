---
title: Documentation Index
scope: Landing page and navigation map for the Maverick documentation set
last-verified: 2026-07-02
---

# Maverick Documentation

This directory holds the conceptual documentation for Maverick — the philosophy,
architecture, workflows, and standards behind the plugin. The machine-readable
skills and agents that *enforce* these ideas live under `src/maverick/` (source)
and are built to the root-level `skills/` and `agents/` directories.

New here? Start with [Overview](overview.md), then read the
[Issue-driven Autonomous Workflow](do-issue-workflow.md).

## Start here

| Doc | What it covers |
| --- | --- |
| [Overview](overview.md) | Architecture and philosophy — the problem Maverick solves and how the pieces fit together. |
| [Vibe Coding](vibe-coders.md) | Why a defined way of working matters when building with LLMs. |
| [Architecture](architecture.md) | The skill/agent catalogue and the upskill system. |

## Workflow & build

| Doc | What it covers |
| --- | --- |
| [Issue-driven Autonomous Workflow](do-issue-workflow.md) | End-to-end flow from GitHub issue through implementation, review, and merge — single story and epic. |
| [Error Handling and Recovery](claude-code-error-handling-and-recovery.md) | Workflow resilience, state persistence, and crash recovery for LLM sessions. |
| [Maverick Build](maverick-build.md) | The build process and the release workflow. |
| [GitHub Labels and Marker Comments](conventions/github-markers.md) | Canonical reference for the labels and machine-readable comments that coordinate multi-instance workflows. |

## Standards & practices

| Doc | What it covers |
| --- | --- |
| [Logging Standards](standards-and-practices/logging-standards.md) | Structured, consistent logging for LLM-generated code. |
| [Alerting Standards](standards-and-practices/alerting-standards.md) | Operational alerting and how Maverick enforces it. |
| [Comprehensive Testing](standards-and-practices/comprehensive-testing.md) | Testing as the primary quality gate. |
| [CI/CD Integration](standards-and-practices/cicd.md) | Pipeline standards, quality gates, and local verification. |
| [Git Workflow](standards-and-practices/git-workflow.md) | Branch strategy, commit conventions, and PR discipline. |
| [Code Review](standards-and-practices/code-review.md) | Maverick's two-stage autonomous review process. |
| [Security Review](standards-and-practices/security-review.md) | Identifying and mitigating vulnerabilities in LLM-generated code. |

## Containment & boundaries

| Doc | What it covers |
| --- | --- |
| [Scope Boundaries](scope-boundaries.md) | The operating envelope — four hard limits an agent must not cross without explicit instruction. |
| [LLM Containment](llm-containment.md) | Defence-in-depth strategies for constraining autonomous agents. |

## Infrastructure

| Doc | What it covers |
| --- | --- |
| [Claude Code Workers](claude-code-workers.md) | Remote compute instances running Claude Code on AWS. |

## Reference

| Doc | What it covers |
| --- | --- |
| [Skills catalogue](skills/maverick-skills.md) | Every skill shipped with the plugin (generated from source configs). |
| [References](references.md) | External documentation links for platforms, tools, and specifications. |

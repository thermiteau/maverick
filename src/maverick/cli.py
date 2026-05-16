"""Unified CLI entry point for claude-maverick."""

import argparse
from importlib.metadata import PackageNotFoundError, version


def _get_version() -> str:
    try:
        v = version("maverick")
    except PackageNotFoundError:
        return "unknown"
    # importlib.metadata returns PEP 440 normalised form (e.g. "1.0.3.dev0"),
    # but pyproject.toml uses the literal "-dev" suffix. Emit the source form
    # so callers can do exact-string comparison against the plugin's
    # pyproject.toml.
    if v.endswith(".dev0"):
        return v[: -len(".dev0")] + "-dev"
    return v


def main():
    parser = argparse.ArgumentParser(
        prog="maverick",
        description="Claude Code provisioning and configuration tool",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {_get_version()}",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # maverick init
    init_parser = subparsers.add_parser("init", help="Initialise project configuration")
    init_parser.add_argument(
        "--override",
        nargs="+",
        metavar="MODULE",
        help="Override detected modules with an explicit list",
    )
    init_parser.add_argument(
        "--add",
        nargs="+",
        metavar="MODULE",
        help="Add modules to the detected set",
    )
    init_parser.add_argument(
        "--remove",
        nargs="+",
        metavar="MODULE",
        help="Remove modules from the detected set",
    )
    init_parser.add_argument(
        "--platform",
        metavar="NAME",
        help="Set the cloud platform (e.g., aws)",
    )
    init_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be detected without writing anything",
    )

    # maverick plugin <action> [--dev]
    plugin_parser = subparsers.add_parser("plugin", help="Manage Claude Code plugin")
    plugin_parser.add_argument(
        "action",
        choices=["install", "uninstall"],
        help="Plugin action to perform",
    )
    plugin_parser.add_argument(
        "--dev",
        action="store_true",
        help="Use local development plugin directory",
    )
    plugin_parser.add_argument(
        "--clean",
        action="store_true",
        help="Also remove project-level maverick artifacts (with uninstall)",
    )

    # maverick clean
    clean_parser = subparsers.add_parser(
        "clean", help="Remove maverick artifacts from the current project"
    )
    clean_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be removed without deleting",
    )

    # maverick build-ami
    subparsers.add_parser("build-ami", help="Bake a Claude Code AMI from Ubuntu 24.04 LTS")

    # maverick instance <action>
    instance_parser = subparsers.add_parser("instance", help="Manage EC2 worker instance")
    instance_parser.add_argument(
        "action",
        choices=["start", "stop", "status"],
        help="Instance action (lifecycle managed by 'maverick infra deploy/destroy')",
    )

    # maverick infra <action>
    infra_parser = subparsers.add_parser("infra", help="Manage AWS infrastructure")
    infra_parser.add_argument(
        "action",
        choices=["deploy", "status", "destroy"],
        help="Infrastructure action to perform",
    )
    infra_parser.add_argument(
        "--include-vpc",
        action="store_true",
        help="Also destroy the VPC stack (default: VPC is preserved)",
    )
    infra_parser.add_argument(
        "--ssh-cidr",
        default="0.0.0.0/0",
        help="CIDR for SSH access to worker instance (default: 0.0.0.0/0)",
    )

    # maverick review-sessions
    review_parser = subparsers.add_parser(
        "review-sessions", help="Review Claude Code session quality"
    )
    review_parser.add_argument(
        "--project",
        required=True,
        metavar="PATH",
        help="Project directory to review sessions for",
    )
    review_parser.add_argument(
        "--session",
        metavar="ID",
        help="Review a specific session by ID (prefix match)",
    )
    review_parser.add_argument(
        "--days",
        type=int,
        metavar="N",
        help="Only review sessions from last N days",
    )
    review_parser.add_argument(
        "--mechanical-only",
        action="store_true",
        default=True,
        help="Skip LLM-powered semantic analysis (default)",
    )
    review_parser.add_argument(
        "--full",
        action="store_true",
        help="Include semantic analysis via agent",
    )
    review_parser.add_argument(
        "--output-dir",
        metavar="PATH",
        help="Override report output directory",
    )

    # maverick worker <action>
    worker_parser = subparsers.add_parser("worker", help="Manage worker daemon")
    worker_parser.add_argument(
        "action",
        choices=["install", "uninstall", "status", "start", "run-once"],
        help="Worker action to perform",
    )

    # Preflight — check prerequisites before an action skill runs
    preflight_parser = subparsers.add_parser(
        "preflight",
        help="Check prerequisites for a Maverick action skill (exit 1 if not met)",
    )
    preflight_parser.add_argument(
        "skill",
        help="Skill name to check (e.g., do-issue-solo, do-epic, do-upskill)",
    )
    preflight_parser.add_argument(
        "--json", action="store_true", help="Emit JSON instead of human-readable text"
    )

    # Integration-status read/write (per-project, committed to .maverick/config.json)
    integration_parser = subparsers.add_parser(
        "integration", help="Read or update Maverick integration milestones"
    )
    integration_sub = integration_parser.add_subparsers(
        dest="integration_action", required=True
    )
    int_get = integration_sub.add_parser(
        "get", help="Print integration status (all flags by default)"
    )
    int_get.add_argument("key", nargs="?", help="Specific flag to read")
    int_get.add_argument(
        "--json", action="store_true", help="Emit JSON instead of human-readable text"
    )
    int_set = integration_sub.add_parser(
        "set", help="Flip an integration flag and save to .maverick/config.json"
    )
    int_set.add_argument("key", help="Flag name (e.g., upskill, alignment)")
    int_set.add_argument(
        "value",
        choices=["true", "false"],
        help="New value for the flag",
    )

    # Coordination / state / worktree / gh-app sub-commands (new workflow)
    from maverick.coord_cli import build_subparsers as _build_coord

    _build_coord(subparsers)

    # do-issue-solo timing reports (#83)
    from maverick.report_cli import build_subparsers as _build_report

    _build_report(subparsers)

    args = parser.parse_args()

    if args.command == "init":
        from maverick.init import main as init_main

        init_main(args)

    elif args.command == "plugin":
        from maverick.plugin import main as plugin_main

        plugin_main(args.action, dev=args.dev, clean=args.clean)

    elif args.command == "clean":
        from maverick.init import clean as clean_main

        clean_main(dry_run=args.dry_run)

    elif args.command == "build-ami":
        from maverick.build_ami import main as build_ami_main

        build_ami_main()

    elif args.command == "instance":
        from maverick.instance import main as instance_main

        instance_main(args.action)

    elif args.command == "infra":
        from maverick.infra import deploy, destroy, status

        if args.action == "destroy":
            destroy(include_vpc=args.include_vpc)
        elif args.action == "deploy":
            deploy(ssh_cidr=args.ssh_cidr)
        else:
            status()

    elif args.command == "review-sessions":
        from maverick.session_review.cli import main as review_main

        review_main(args)

    elif args.command == "worker":
        from maverick.worker import main as worker_main

        worker_main(args.action)

    elif args.command == "integration":
        from maverick.integration_cli import main as integration_main

        integration_main(args)

    elif args.command == "preflight":
        import sys as _sys

        from maverick.preflight_cli import main as preflight_main

        _sys.exit(preflight_main(args))

    elif args.command in (
        "coord",
        "dag",
        "state",
        "worktree",
        "gh-app",
        "gh-state",
        "task-progress",
        "issue",
        "git-workflow",
        "report",
    ):
        import sys as _sys

        from maverick.coord_cli import dispatch as _dispatch

        _sys.exit(_dispatch(args))


if __name__ == "__main__":
    main()

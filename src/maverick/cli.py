"""Unified CLI entry point for claude-maverick."""

import argparse
import sys


def main():
    parser = argparse.ArgumentParser(
        prog="maverick",
        description="Claude Code provisioning and configuration tool",
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
    instance_parser = subparsers.add_parser("instance", help="Manage EC2 instances")
    instance_parser.add_argument(
        "action",
        choices=["create", "start", "stop", "status", "terminate"],
        help="Instance action to perform",
    )

    # maverick infra <action>
    infra_parser = subparsers.add_parser("infra", help="Manage AWS infrastructure")
    infra_parser.add_argument(
        "action",
        choices=["deploy", "status", "destroy"],
        help="Infrastructure action to perform",
    )

    # maverick worker <action>
    worker_parser = subparsers.add_parser("worker", help="Manage worker daemon")
    worker_parser.add_argument(
        "action",
        choices=["install", "uninstall", "status", "start", "run-once"],
        help="Worker action to perform",
    )

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
        from maverick.infra import deploy, status, destroy

        actions = {"deploy": deploy, "status": status, "destroy": destroy}
        actions[args.action]()

    elif args.command == "worker":
        from maverick.worker import main as worker_main

        worker_main(args.action)


if __name__ == "__main__":
    main()

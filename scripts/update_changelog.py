"""Insert a new version section into CHANGELOG.md."""

import re
import sys


def main() -> None:
    new_version = sys.argv[1]
    today = sys.argv[2]
    prev_tag = sys.argv[3] if len(sys.argv) > 3 else ""
    tag = "v" + new_version

    with open("CHANGELOG.md") as f:
        content = f.read()

    # Insert new version section after ## [Unreleased]
    content = content.replace(
        "## [Unreleased]",
        f"## [Unreleased]\n\n## [{new_version}] - {today}",
        1,
    )

    # Update comparison links at the bottom
    # Change [Unreleased] link to compare from new tag
    content = re.sub(
        r"\[Unreleased\]: (https://github\.com/[^/]+/[^/]+)/compare/.*\.\.\.HEAD",
        rf"[Unreleased]: \g<1>/compare/{tag}...HEAD",
        content,
    )

    # Add new version link before existing version links
    if prev_tag:
        unreleased_link_pattern = (
            r"(\[Unreleased\]: https://github\.com/[^\n]+\n)"
        )
        repo_match = re.search(
            r"\[Unreleased\]: (https://github\.com/[^/]+/[^/]+)/", content
        )
        if repo_match:
            repo_url = repo_match.group(1)
            new_link = f"[{new_version}]: {repo_url}/compare/{prev_tag}...{tag}\n"
            content = re.sub(
                unreleased_link_pattern, r"\g<1>" + new_link, content
            )

    with open("CHANGELOG.md", "w") as f:
        f.write(content)


if __name__ == "__main__":
    main()

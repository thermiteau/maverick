"""Update version strings in plugin JSON files."""

import json
import sys


def update_json(path: str, updates: list[tuple[list[str | int], str]]) -> None:
    with open(path) as f:
        data = json.load(f)
    for keys, value in updates:
        obj = data
        for k in keys[:-1]:
            obj = obj[k]
        obj[keys[-1]] = value
    with open(path, "w") as f:
        json.dump(data, f, indent=2)
        f.write("\n")


def main() -> None:
    version = sys.argv[1]

    update_json(
        ".claude-plugin/plugin.json",
        [
            (["version"], version),
        ],
    )

    update_json(
        ".claude-plugin/marketplace.json",
        [
            (["version"], version),
            (["plugins", 0, "version"], version),
        ],
    )

    update_json(
        ".cursor-plugin/cursor.plugin.json",
        [
            (["version"], version),
        ],
    )


if __name__ == "__main__":
    main()

"""Generate skills/upskill/topics.json from the upskill config."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

from maverick.models import TopicConfig
from maverick.registry import SKILLS_OUTPUT_DIR

TEMPLATES_DIR = Path(__file__).resolve().parent / "skills"


def _load_topics(templates_dir: Path = TEMPLATES_DIR) -> list[TopicConfig]:
    """Dynamically load TOPICS from the upskill config.py."""
    config_path = templates_dir / "upskill" / "config.py"
    spec = importlib.util.spec_from_file_location("_upskill_config", config_path)
    module = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
    spec.loader.exec_module(module)  # type: ignore[union-attr]
    return module.TOPICS


def generate_topics_json(output_dir: Path = SKILLS_OUTPUT_DIR) -> Path:
    """Generate topics.json from the upskill topic configs."""
    topics = _load_topics()
    entries = [
        {
            "topic": t.topic,
            "prompt": t.prompt,
            "bestPracticeSkill": f"skills/{t.best_practice_skill}/SKILL.md",
        }
        for t in topics
    ]

    output_path = output_dir / "upskill" / "topics.json"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(entries, indent=2) + "\n")
    return output_path


def main() -> None:
    output = generate_topics_json()
    print(f"Generated {output}")


if __name__ == "__main__":
    main()

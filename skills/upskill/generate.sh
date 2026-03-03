#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
CONFIG_FILE="$SCRIPT_DIR/topics.json"
TEMPLATE_FILE="$SCRIPT_DIR/SKILL.md"

# --- Prerequisite checks ---

if ! command -v jq &>/dev/null; then
  echo "Error: jq is required but not installed." >&2
  exit 1
fi

if ! command -v claude &>/dev/null; then
  echo "Error: claude CLI is required but not installed." >&2
  exit 1
fi

if [[ ! -f "$CONFIG_FILE" ]]; then
  echo "Error: Config file not found: $CONFIG_FILE" >&2
  exit 1
fi

if [[ ! -f "$TEMPLATE_FILE" ]]; then
  echo "Error: Template file not found: $TEMPLATE_FILE" >&2
  exit 1
fi

# --- Read config ---

TOPIC_COUNT=$(jq 'length' "$CONFIG_FILE")

if [[ "$TOPIC_COUNT" -eq 0 ]]; then
  echo "No topics found in $CONFIG_FILE"
  exit 0
fi

echo "Found $TOPIC_COUNT topic(s) to generate."

# --- Build prompt for a topic ---

build_prompt() {
  local topic="$1"
  local custom_prompt="$2"
  local best_practice_path="$3"

  local prompt=""
  local template_content
  template_content=$(<"$TEMPLATE_FILE")

  # Part 1: Custom prompt
  prompt="$custom_prompt"
  prompt+=$'\n\n'

  # Part 2: Best-practice content (if provided)
  if [[ "$best_practice_path" != "null" && -n "$best_practice_path" ]]; then
    local full_path="$PROJECT_ROOT/$best_practice_path"
    if [[ -f "$full_path" ]]; then
      prompt+="## Best Practice Reference"
      prompt+=$'\n\n'
      prompt+=$(<"$full_path")
      prompt+=$'\n\n'
    else
      echo "Warning: Best practice skill not found: $full_path (skipping embed)" >&2
    fi
  fi

  # Part 3: Generation template
  prompt+="## Generation Instructions"
  prompt+=$'\n\n'
  prompt+="$template_content"
  prompt+=$'\n\n'
  prompt+="Generate the project skill for topic: \"$topic\""

  printf '%s' "$prompt"
}

# --- Launch parallel headless invocations ---

declare -a PIDS=()
declare -a TOPICS=()
LOG_DIR=$(mktemp -d)

for i in $(seq 0 $((TOPIC_COUNT - 1))); do
  TOPIC=$(jq -r ".[$i].topic" "$CONFIG_FILE")
  CUSTOM_PROMPT=$(jq -r ".[$i].prompt" "$CONFIG_FILE")
  BEST_PRACTICE=$(jq -r ".[$i].bestPracticeSkill" "$CONFIG_FILE")

  FULL_PROMPT=$(build_prompt "$TOPIC" "$CUSTOM_PROMPT" "$BEST_PRACTICE")

  echo "Launching: $TOPIC"

  env -u CLAUDECODE claude -p "$FULL_PROMPT" \
    --allowedTools "Read,Glob,Grep,Write,Bash(mkdir *)" \
    --output-format json \
    > "$LOG_DIR/$TOPIC.json" 2>&1 &

  PIDS+=($!)
  TOPICS+=("$TOPIC")
done

# --- Wait and collect results ---

FAILED=0

for i in "${!PIDS[@]}"; do
  PID="${PIDS[$i]}"
  TOPIC="${TOPICS[$i]}"

  if wait "$PID"; then
    echo "OK: $TOPIC"
  else
    echo "FAIL: $TOPIC (see $LOG_DIR/$TOPIC.json)" >&2
    FAILED=$((FAILED + 1))
  fi
done

# --- Summary ---

echo ""
echo "Complete: $((TOPIC_COUNT - FAILED))/$TOPIC_COUNT succeeded."

if [[ "$FAILED" -gt 0 ]]; then
  echo "Logs: $LOG_DIR"
  exit 1
fi

rm -rf "$LOG_DIR"


# Init Maverick Project

Set up the current repository for Maverick by creating the project-level config directory, docs and Claude Skills.

## Dispatch

Dispatch the **maverick** agent with task `init` and any user-provided arguments. The agent will follow the process below and return a structured result.

## Process

1. Create the `.maverick/` directory in the project root (the git repository root)
2. Write `.maverick/settings.json` containing `{}` (empty object — project-specific overrides go here)
3. Run the skill /maverick:tech-docs
4. Run the skill /maverick:upskill

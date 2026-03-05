---
title: Maverick Build
scope: Understanding the maverick build process and the rationale behind it
relates-to:
  - maverick-install.md
last-verified: 2026-03-02
---

# Maverick Build

## Templating

The maverick plaugin uses tempaltes to create the skills and agents that make up the Claude Code plaugin. While this adds a layer of complexity, it allows the frontmatter to be validated and ensures that references to other sklills can be validated.

The build process uses the template under a given skills folder `SKILL.md.template` and the config file `config.py` that holds all the variables.

This way we can be sure that cross references are accurate and that the Claude skill fronmatter schema is adhered to

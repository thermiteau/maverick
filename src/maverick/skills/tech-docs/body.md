
# Technical Documentation

Produce technical documentation that explains **what** systems do, **how** they interact, and **why** specific choices were made.

**Primary audience: LLMs.** These docs will be loaded into LLM context windows during development tasks. Every token must earn its place. Write for machine comprehension first — dense, precise, and structurally consistent. Avoid prose padding, narrative flow, and filler sentences that a human might appreciate but an LLM gains nothing from.

Avoid documenting business processes or product capabilities.

## Process

```dot
digraph docs {
    "Understand the request" [shape=box];
    "Explore the codebase" [shape=box];
    "Audit existing docs" [shape=diamond];
    "Identify scope" [shape=box];
    "Write / update documentation" [shape=box];
    "Validate accuracy" [shape=diamond];
    "Done" [shape=box];
    "Revise" [shape=box];

    "Understand the request" -> "Explore the codebase";
    "Explore the codebase" -> "Audit existing docs";
    "Audit existing docs" -> "Identify scope" [label="docs exist"];
    "Audit existing docs" -> "Identify scope" [label="no docs"];
    "Identify scope" -> "Write / update documentation";
    "Write / update documentation" -> "Validate accuracy";
    "Validate accuracy" -> "Done" [label="accurate"];
    "Validate accuracy" -> "Revise" [label="gaps found"];
    "Revise" -> "Validate accuracy";
}
```

### 1. Understand the Request

Clarify what needs documenting:

- A specific component, service, or subsystem
- An architectural overview or cross-cutting concern
- A design decision or technology choice
- An update to existing documentation after a change

### 2. Explore the Codebase

Before writing anything, read the relevant source code:

- Use Glob, Grep, Read, and subagents to understand actual behaviour
- Examine dependency files to understand the technology stack
- Review configuration and infrastructure files for deployment context
- Look at test files to understand expected behaviours and edge cases

### 3. Audit Existing Documentation

Check whether a `docs/` directory (or `docs/technical/`) already exists. If it does, read every document in it before writing anything new.

For each existing document, assess:

- **Structure compliance** — does it follow the Document Structure defined in this skill? (frontmatter, Overview, Core Content, Integration Points, Design Decisions)
- **Accuracy** — do factual claims still match the current source code? Flag anything outdated or incorrect.
- **Token efficiency** — does it follow the writing style and token budget guidelines? Look for prose padding, narrative filler, or documents exceeding 500 lines.
- **Diagram coverage** — do documents describing interactions or flows include Mermaid diagrams?
- **Cross-references** — are `relates-to` links in frontmatter correct and complete?

After auditing, classify each document as:

| Status | Action |
| --- | --- |
| Compliant and accurate | Leave unchanged |
| Accurate but non-compliant | Rewrite to match this skill's structure and standards |
| Outdated or inaccurate | Update with verified information from the current codebase |
| Redundant or overlapping | Consolidate into a single document |

Then identify **gaps** — areas of the codebase that have no documentation coverage. Use the codebase exploration from step 2 to determine what is missing.

### 4. Identify Scope

Determine the documentation boundary:

- What is being documented (and what is explicitly out of scope)
- Where the documentation should live (co-located with code or in a central docs directory)
- Whether this is a new document, an update to an existing one, or a rewrite of a non-compliant one

### 5. Write / Update Documentation

Follow the structure and standards below. When updating existing documents, preserve any accurate content and restructure it to comply with this skill's standards rather than rewriting from scratch.

### 6. Validate Accuracy

Cross-reference every factual claim with the source code. If you cannot verify something, say so rather than guessing.

## Documentation Principles

### Include

- **Purpose and function**: What each component does and why it exists
- **Technology choices**: What is used and why it was selected
- **Integration points**: How components communicate and depend on each other
- **Data flow**: How data moves through the system
- **Architectural patterns**: Design patterns employed and their rationale
- **Accessibility patterns**: ARIA attribute usage, focus management, keyboard navigation, screen reader support, and WCAG compliance level. Especially important for government or public-sector projects.
- **Validation and business rules**: Form validation logic, required field rules, conditional visibility, and domain constraints that the application enforces
- **Mermaid diagrams**: Every document describing interactions or flows must include at least one diagram

### Exclude

- **Implementation code**: No function bodies, algorithms, or internal logic as code blocks
- **Infrastructure configuration**: No CDK, Terraform, Docker Compose, or config file content
- **CLI commands**: No terminal commands or deployment scripts (see exception below)
- **API endpoint definitions**: No route paths, request/response schemas, or curl examples

### Include as Structured Tables (Not Code Blocks)

- **Component/module public API**: Props, parameters, exported types, and return values — documented as tables, not code snippets
- **Context/hook API surface**: What a context provider or hook exposes to consumers

### Optional: Developer Onboarding Section

When documenting a full project (not a single component), include a brief onboarding section in `architecture-overview.md` or a dedicated `getting-started.md`:

- Prerequisites (runtime versions, package manager)
- Install and run commands
- Key scripts (build, test, lint)

Keep to under 20 lines. This is the one context where CLI commands are acceptable.

## Document Structure

Every document must start with a YAML frontmatter block. This gives an LLM immediate context about what the document covers without reading the full body.

```markdown
---
title: <descriptive title>
scope: <component | service | architecture | decision>
relates-to: [list of other doc filenames this connects to]
last-verified: <YYYY-MM-DD when last checked against source code>
---

## Overview

<1-2 sentences: what this covers, stated as facts not narrative.>

## <Core Content>

<Main documentation. Use H2/H3 headings as section labels. Prefer bullet points and tables over paragraphs. Each section should be independently useful — an LLM may retrieve a single section, not the whole document.>

## Integration Points

<How this component connects to others. Include a Mermaid diagram.>

## Design Decisions

<Decision: rationale format. No preamble.>
```

### Token Budget

Docs are loaded into LLM context alongside code, conversation history, and tool results. Context is finite and expensive.

- **Target: 200-500 lines per document.** If a document exceeds this, split it.
- Use bullet points and tables instead of paragraphs — same information, fewer tokens
- State facts directly: "Auth uses JWT with RS256" not "The authentication system has been designed to utilise JSON Web Tokens using the RS256 algorithm"
- Define terms inline on first use with parenthetical notation: "The gateway (API entry point handling routing and auth) forwards requests to..."
- Omit transition sentences, introductory phrasing, and summaries of what was just said
- Prefer structured lists over prose for enumerating components, dependencies, or flows

### File Organisation

- Store all documentation under `docs/technical/`
- Create **separate files** for distinct topics rather than monolithic documents
- Use `kebab-case.md` naming (e.g. `authentication-architecture.md`)
- Each file should be self-contained but may cross-reference others via `relates-to` in frontmatter
- Maintain an `index.md` in `docs/technical/` listing all documents with one-line descriptions — this serves as the entry point for LLM context loading

### Sizing

| Task size                           | Documentation depth                                |
| ----------------------------------- | -------------------------------------------------- |
| Trivial (config, minor change)      | 2-3 sentences in an existing doc or commit message |
| Small (single component)            | Overview + core content (under 200 lines)          |
| Medium (feature, service)           | Full document structure (200-500 lines)            |
| Large (cross-cutting, architecture) | Split into multiple focused documents              |

### Within a Document

Scale section depth to component complexity. Indicators that a component needs deeper coverage:

- File exceeds 300 lines
- Contains business/domain logic (rule engines, calculations, transformations)
- Has multiple distinct output modes (e.g., screen rendering, PDF export, print view)
- Serves as an aggregation point for data from multiple sources

For these components, document each distinct responsibility separately rather than summarising the whole.

## Mermaid Diagram Standards

Use diagrams to visualise:

- **Service interactions**: `sequenceDiagram` or `flowchart`
- **Data flows**: `flowchart` or `sequenceDiagram`
- **Architecture overviews**: `flowchart` or `C4Context`
- **State transitions**: `stateDiagram-v2`

Guidelines:

- Every diagram must have a descriptive title
- Use clear, descriptive node labels — not abbreviations or internal variable names
- Keep diagrams focused on one concept; prefer multiple simple diagrams over one complex one
- Aim for no more than 15-20 nodes per diagram

## Writing Style

- **Dense, not verbose**: State facts. Skip introductions, transitions, and conclusions. An LLM does not need to be "eased into" a topic.
- **Precise**: Use exact technology names and versions. "PostgreSQL 16 with row-level security" not "a relational database with access controls".
- **Consistent terminology**: Use the same term for the same concept everywhere. Define domain terms inline on first use.
- **Structured over narrative**: Prefer `key: value` patterns, bullet lists, and tables. Reserve prose for explaining *why* — rationale that cannot be expressed as a list.

## Validation Checklist

Before finalising documentation:

- [ ] All factual claims verified against source code
- [ ] Mermaid diagrams render correctly (valid syntax)
- [ ] No implementation code, config snippets, or CLI commands included (API surface tables are acceptable)
- [ ] Cross-references use correct relative paths
- [ ] Document is under 500 lines (split if larger)
- [ ] YAML frontmatter present with title, scope, relates-to, last-verified
- [ ] `docs/technical/index.md` updated if this is a new document
- [ ] Bullet points and tables used instead of prose where possible
- [ ] All public exports from documented modules are covered (check for multiple exports per file)
- [ ] Numbering, terminology, and facts are consistent across all documents in the set

---
name: mav-bp-versioning
description: Versioning and deprecation conventions for projects producing libraries, APIs, or SDKs. Covers semantic versioning, changelog maintenance, deprecation policies, and breaking change management. Applied when releasing or reviewing versioned artifacts.
---

# Versioning & Deprecation Standards

Ensure all versioned artifacts follow semantic versioning, maintain changelogs, and handle breaking changes and deprecations responsibly. Consumers of your library, API, or SDK depend on predictable version semantics to manage their own software safely.

## Principles

1. **Semantic Versioning for public interfaces** — version numbers communicate compatibility guarantees. Follow SemVer strictly for anything with external consumers.
2. **Breaking changes require a major bump** — consumers must be able to trust that minor and patch updates will not break their code.
3. **Changelogs are maintained** — every release has a human-readable summary of what changed, not just a list of commits.
4. **Deprecate before removing** — features, endpoints, and APIs are deprecated with advance notice before they are removed in a future major version.

## Scope

These standards apply primarily to projects that produce **versioned artifacts consumed by others**:

- Libraries and packages published to registries (npm, PyPI, crates.io, Maven Central, NuGet)
- APIs with external consumers (public REST APIs, GraphQL APIs, gRPC services)
- SDKs and client libraries
- Shared internal packages consumed by other teams or services
- CLI tools with scripted usage

**Internal applications** (web apps, backend services with no external API consumers) may use simplified versioning (e.g., date-based versions, git SHAs, or auto-incrementing build numbers) since they do not have external compatibility contracts. However, if an internal service exposes an API consumed by other internal services, the API versioning standards in this skill still apply to that API surface.

## Semantic Versioning

All versioned artifacts must follow [Semantic Versioning 2.0.0](https://semver.org/) (`MAJOR.MINOR.PATCH`):

| Component | When to increment | Example |
| --------- | ----------------- | ------- |
| **MAJOR** | Incompatible API changes — removing or renaming public functions, changing behaviour, removing endpoints, changing data formats | `1.4.2` -> `2.0.0` |
| **MINOR** | Backwards-compatible new functionality — new functions, new endpoints, new optional parameters, new configuration options | `1.4.2` -> `1.5.0` |
| **PATCH** | Backwards-compatible bug fixes — fixing incorrect behaviour, security patches, performance improvements with no API change | `1.4.2` -> `1.4.3` |

### What Constitutes a Breaking Change

A change is breaking if any existing consumer code could fail, produce different results, or require modification after upgrading:

- Removing or renaming a public function, method, class, or type
- Changing the signature of a public function (adding required parameters, changing return type)
- Removing or renaming an API endpoint
- Changing the structure of a response body (removing fields, changing types)
- Changing default behaviour that consumers may rely on
- Dropping support for a previously supported runtime, language version, or platform
- Changing error codes or error response formats
- Removing or renaming configuration options or environment variables

### What is NOT a Breaking Change

- Adding a new public function, method, or class
- Adding a new optional parameter with a default value
- Adding a new field to a response body (assuming consumers ignore unknown fields)
- Adding a new API endpoint
- Fixing a bug (the previous behaviour was incorrect, not a feature)
- Performance improvements with no API surface change
- Adding new configuration options with sensible defaults

## Breaking Change Management

Breaking changes are sometimes necessary, but they must be handled deliberately.

### Process

1. **Deprecate first** — mark the feature, function, or endpoint as deprecated in the current version (see Deprecation Policy below)
2. **Communicate** — document the upcoming removal in the changelog, release notes, and migration guide
3. **Provide a migration path** — tell consumers exactly what to use instead and how to migrate
4. **Wait for a deprecation period** — give consumers time to migrate (at least one minor release cycle, ideally more)
5. **Remove in a major version** — bundle all removals of deprecated features into the next major release
6. **Publish a migration guide** — for major versions with breaking changes, publish a dedicated migration document

### Migration Guide Content

| Section | Contents |
| ------- | -------- |
| **Overview** | Summary of breaking changes and why they were made |
| **Step-by-step migration** | Ordered instructions for updating consumer code |
| **Before/after examples** | Code snippets showing old usage and new usage |
| **Automated migration** | Codemods or scripts if available |
| **Timeline** | When the old version will stop receiving patches |

## Changelog Maintenance

Every project with versioned releases must maintain a changelog that is readable by humans, not just a dump of commit messages.

### Format

Use one of these approaches:

| Approach | File/Location | Tooling |
| -------- | ------------- | ------- |
| **CHANGELOG.md** | Root of repository | Manual or generated via `conventional-changelog`, `changelogen`, `git-cliff` |
| **GitHub Releases** | GitHub release page | Manual or generated via `release-please`, `semantic-release`, GitHub auto-generated notes |
| **Both** | CHANGELOG.md + GitHub Releases | Best practice for public packages — CHANGELOG.md for repository readers, GitHub Releases for registry/notification consumers |

### Changelog Entry Structure

Each version entry should contain:

```markdown
## [1.5.0] - 2025-03-15

### Added
- New `export()` function for batch data retrieval (#142)
- Support for custom retry policies in HTTP client (#155)

### Changed
- Default timeout increased from 5s to 30s (#160)

### Deprecated
- `fetchAll()` is deprecated in favour of `export()` — will be removed in 2.0.0 (#142)

### Fixed
- Connection pool leak when requests timeout (#148)
- Incorrect pagination cursor encoding for Unicode content (#151)

### Security
- Updated `xmlparser` dependency to fix CVE-2025-XXXX (#153)
```

### Rules

- **Update the changelog in the same PR as the code change** — do not batch changelog updates at release time
- **Reference issue or PR numbers** — every entry links to its source for traceability
- **Use categories** — Added, Changed, Deprecated, Removed, Fixed, Security (per [Keep a Changelog](https://keepachangelog.com/))
- **Write for consumers** — describe impact, not implementation details. "Added retry support" not "refactored HTTPClient to accept RetryPolicy in constructor"
- **Automate where possible** — use conventional commits with automated changelog generation to reduce manual effort

## Deprecation Policy

Deprecation is a contract with consumers: "this will go away, here is your notice and here is what to use instead."

### Marking Deprecation in Code

Use the language's built-in deprecation mechanism:

```python
# Python
import warnings

def old_function():
    warnings.warn(
        "old_function() is deprecated, use new_function() instead. "
        "Will be removed in 2.0.0.",
        DeprecationWarning,
        stacklevel=2,
    )
    return new_function()
```

```typescript
// TypeScript/JavaScript — JSDoc
/**
 * @deprecated Use `newFunction()` instead. Will be removed in 2.0.0.
 */
export function oldFunction(): void {
  return newFunction();
}
```

```java
// Java
@Deprecated(since = "1.5.0", forRemoval = true)
public void oldMethod() {
    newMethod();
}
```

```rust
// Rust
#[deprecated(since = "1.5.0", note = "Use new_function() instead")]
pub fn old_function() {
    new_function()
}
```

### Deprecation Rules

- **State what replaces it** — every deprecation message must name the replacement
- **State when it will be removed** — "will be removed in 2.0.0" or "will be removed after 2025-06-01"
- **Document in the changelog** — add a `Deprecated` entry in the release that introduces the deprecation
- **Keep the deprecated code working** — deprecated does not mean broken. It must continue to function until removal.
- **Remove only in a major version** — deprecated features are removed in the next major release, not in minor or patch releases
- **Track usage** — for APIs, log calls to deprecated endpoints to measure migration progress before removal

## Pre-Release Versions

For versions that are not yet stable, use SemVer pre-release identifiers:

| Stage | Format | Meaning |
| ----- | ------ | ------- |
| **Alpha** | `2.0.0-alpha.1`, `2.0.0-alpha.2` | Early development, API may change significantly, not for production use |
| **Beta** | `2.0.0-beta.1`, `2.0.0-beta.2` | Feature-complete, API mostly stable, suitable for testing but not production |
| **Release Candidate** | `2.0.0-rc.1`, `2.0.0-rc.2` | Production-ready candidate, only critical fixes before final release |

### Rules

- **Pre-release versions have no stability guarantees** — breaking changes between alpha/beta versions do not require a major bump
- **Do not publish pre-releases to the default registry tag** — use `npm publish --tag next`, `pip install package==2.0.0a1`, etc. so that default installs get the stable version
- **Document pre-release status clearly** — README, package description, and changelog should all indicate that the version is not stable
- **Increment the pre-release number** for each new pre-release: `alpha.1`, `alpha.2`, `alpha.3`

## Relationship to API Versioning

This skill covers **artifact versioning** — the version number of a package, library, or release.

The `mav-bp-api-design` skill covers **API endpoint versioning** — URL path versioning (`/v1/users`), header-based versioning, and API deprecation processes.

The two are related but distinct:
- A library at version `1.5.0` may expose an API at `/v2/` — the artifact version and API version are independent
- A breaking change to a public API requires both an API version bump (if using URL versioning) and a major artifact version bump
- Deprecation policies apply to both: deprecated library functions and deprecated API endpoints follow the same principle of notice, migration path, and removal only in major versions

## Detecting Versioning Issues in Code Review

| Pattern | Issue | Fix |
| ------- | ----- | --- |
| Breaking change with only a minor or patch bump | SemVer violation | Bump major version |
| Removed function with no prior deprecation | Consumer breakage without notice | Deprecate first, remove in next major |
| Changelog not updated with code change | Missing release documentation | Add changelog entry in the same PR |
| Deprecation message with no replacement named | Unhelpful deprecation | State what to use instead and when removal happens |
| Pre-release published to default registry tag | Unstable version installed by default | Use `--tag next` or equivalent |
| Version bump without changelog entry | Consumers cannot understand what changed | Add changelog entry before release |
| Code removal in minor/patch release | Breaking change in non-major version | Move removal to next major version |
| No migration guide for major version | Consumers blocked on upgrade | Write a migration guide with before/after examples |
| Deprecated code no longer functions | Broken deprecation contract | Fix deprecated code path — it must work until removal |
| Multiple breaking changes across minor releases | Death by a thousand cuts for consumers | Batch breaking changes into a single major release |

<!-- maverick-plugin-version: 3.3.0 -->

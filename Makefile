.PHONY: generate generate-topics build release lint format typecheck test

lint: ## Run ruff linter
	uv run ruff check .

typecheck: ## Run pyright type checker
	uv run pyright


generate: ## Render all skill and agent templates
	cd src && uv run python -m maverick.registry

generate-topics: ## Generate skills/upskill/topics.json from upskill config
	cd src && uv run python -m maverick.generate_topics

build: generate-topics generate

test: ## Run unit tests
	uv run pytest tests/unit/ -v

release: ## Create a patch release (bump patch version, tag, merge to main)
	./scripts/release.sh patch

release-minor: ## Create a minor release (bump minor version, tag, merge to main)
	./scripts/release.sh minor

release-major: ## Create a major release (bump major version, tag, merge to main)
	./scripts/release.sh major
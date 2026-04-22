.PHONY: generate generate-topics build release lint format typecheck test infra

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

release: ## Create a patch release (PR to main, squash merge, tag on main)
	./scripts/release.sh patch

release-minor: ## Create a minor release (PR to main, squash merge, tag on main)
	./scripts/release.sh minor

release-major: ## Create a major release (PR to main, squash merge, tag on main)
	./scripts/release.sh major

infra: ## Deploy AWS infrastructure (use ACTION=status or ACTION=destroy to override)
	uv run maverick infra $(or $(ACTION),deploy)

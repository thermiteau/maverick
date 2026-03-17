.PHONY: generate generate-topics build release lint format typecheck

lint: ## Run ruff linter
	uv run ruff check .

typecheck: ## Run pyright type checker
	uv run pyright


generate: ## Render all skill and agent templates
	cd src && python -m maverick.registry

generate-topics: ## Generate skills/upskill/topics.json from upskill config
	cd src && python -m maverick.generate_topics

build: generate-topics generate

release: build ## Create a release (usage: make release VERSION=0.2.0)
	bash scripts/release.sh $(VERSION)

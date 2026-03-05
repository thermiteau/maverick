.PHONY: generate-skills generate-agents generate-topics build release

generate-skills: ## Render all SKILL.md files from templates
	cd src && python -m maverick.registry

generate-agents: ## Render all agent .md files from templates
	cd src && python -m maverick.registry

generate-topics: ## Generate skills/upskill/topics.json from upskill config
	cd src && python -m maverick.generate_topics

build: generate-topics generate-skills generate-agents

release: ## Create a release (usage: make release VERSION=0.2.0)
	bash scripts/release.sh $(VERSION)

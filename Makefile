.PHONY: generate-skills generate-agents generate-topics build

generate-skills: ## Render all SKILL.md files from templates
	cd src && python -m maverick.registry

generate-agents: ## Render all agent .md files from templates
	cd src && python -m maverick.registry

generate-topics: ## Generate skills/upskill/topics.json from upskill config
	cd src && python -m maverick.generate_topics

build: generate-skills generate-topics

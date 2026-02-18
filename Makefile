.PHONY: help docker-start docker-stop docker-logs docker-ps docker-clean docker-rebuild

# Colors
GREEN := \033[0;32m
YELLOW := \033[1;33m
BLUE := \033[0;34m
NC := \033[0m

help: ## Show this help
	@echo "$(BLUE)📋 Available commands (from project root):$(NC)"
	@echo ""
	@echo "$(YELLOW)Docker (Forward to docker/Makefile):$(NC)"
	@grep -E '^docker-' Makefile | grep '##' | awk 'BEGIN {FS = ":.*?## "}; {printf "$(GREEN)%-20s$(NC) %s\n", $$1, $$2}'
	@echo ""
	@echo "Ex: make docker-start"

docker-start: ## Start Docker container
	cd docker && make docker-start

docker-stop: ## Stop Docker container
	cd docker && make docker-stop

docker-logs: ## View Docker logs
	cd docker && make docker-logs

docker-ps: ## View Docker container status
	cd docker && make docker-ps

docker-restart: ## Restart Docker container
	cd docker && make docker-restart

docker-build: ## Build Docker image
	cd docker && make docker-build

docker-clean: ## Clean Docker (becarefull)
	cd docker && make docker-clean

docker-rebuild: ## Rebuild without cache
	cd docker && make docker-rebuild

docker-shell: ## Open shell container
	cd docker && make docker-shell

docker-stats: ## See statistics
	cd docker && make docker-stats

docker-health: ## Check healt status
	cd docker && make docker-health

.DEFAULT_GOAL := help

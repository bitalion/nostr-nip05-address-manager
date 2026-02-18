.PHONY: help docker-build docker-start docker-stop docker-logs docker-ps docker-clean docker-rebuild

# Colors for output
GREEN := \033[0;32m
YELLOW := \033[1;33m
BLUE := \033[0;34m
NC := \033[0m # No Color

help: ## Show this help
	@echo "$(BLUE)📋 Available commands (run from docker/):$(NC)"
	@echo ""
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "$(GREEN)%-20s$(NC) %s\n", $$1, $$2}'
	@echo ""
	@echo "Example: make docker-start"
	@echo ""
	@echo "$(YELLOW)📍 Location: docker/$(NC)"

docker-build: ## Build Docker image
	@echo "$(BLUE)🔨 Building Docker image...$(NC)"
	docker-compose build

docker-start: ## Start application with docker-compose
	@echo "$(BLUE)🚀 Starting application...$(NC)"
	./scripts/docker-start.sh

docker-stop: ## Stop application
	@echo "$(BLUE)🛑 Stopping application...$(NC)"
	./scripts/docker-stop.sh

docker-logs: ## View logs in real time
	@echo "$(BLUE)📋 Showing logs...$(NC)"
	docker-compose logs -f nip05-app

docker-ps: ## View container status
	@echo "$(BLUE)📊 Container status:$(NC)"
	docker-compose ps

docker-restart: ## Restart containers
	@echo "$(BLUE)🔄 Restarting...$(NC)"
	docker-compose restart

docker-clean: ## Delete containers and volumes (CAUTION)
	@echo "$(YELLOW)⚠️  Deleting containers and volumes...$(NC)"
	docker-compose down -v
	@echo "$(GREEN)✅ Cleanup completed$(NC)"

docker-rebuild: ## Rebuild from scratch (without cache)
	@echo "$(BLUE)🔨 Rebuilding image (without cache)...$(NC)"
	docker-compose build --no-cache
	@echo "$(YELLOW)ℹ️  Now run: make docker-start$(NC)"

docker-shell: ## Open shell in container
	@echo "$(BLUE)🔧 Opening shell...$(NC)"
	docker exec -it nip05-app bash

docker-stats: ## Show resource statistics
	@echo "$(BLUE)📊 Resource statistics:$(NC)"
	docker stats nip05-app

docker-health: ## Check health status
	@echo "$(BLUE)💚 Health status:$(NC)"
	docker inspect nip05-app --format='{{.State.Health.Status}}'

.DEFAULT_GOAL := help

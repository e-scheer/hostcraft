.PHONY: help dev dev-build dev-down dev-logs dev-shell dev-manage prod prod-down prod-logs build clean

COMPOSE_DEV  = docker compose -f docker-compose.dev.yml
COMPOSE_PROD = docker compose

help:
	@echo "hostcraft — make targets:"
	@echo ""
	@echo "  Development (everything in Docker, no host tooling):"
	@echo "    dev          start dev stack (minecraft + django + vite, hot reload)"
	@echo "    dev-build    rebuild dev images"
	@echo "    dev-down     stop dev stack"
	@echo "    dev-logs     follow dev stack logs"
	@echo "    dev-shell    open a bash shell in the backend container"
	@echo "    dev-manage   run a Django manage.py command (use ARGS=...)"
	@echo ""
	@echo "  Production-style:"
	@echo "    prod         start production stack (Gunicorn + embedded SPA)"
	@echo "    prod-down    stop production stack"
	@echo "    prod-logs    follow production stack logs"
	@echo "    build        build production Docker image"
	@echo ""
	@echo "  Reset:"
	@echo "    clean        nuke ALL volumes (db, node_modules, MC world)"

dev:
	$(COMPOSE_DEV) up

dev-build:
	$(COMPOSE_DEV) build

dev-down:
	@# Drop sidecars the panel spawns at runtime (Playit agent, …). They
	@# aren't in compose, so ``compose down`` leaves them attached to the
	@# network and the teardown bails with "active endpoints".
	@docker ps -a --filter "label=hostcraft.role=playit-agent" --format "{{.ID}}" \
		| xargs -r docker rm -f >/dev/null
	$(COMPOSE_DEV) down

dev-logs:
	$(COMPOSE_DEV) logs -f

dev-shell:
	$(COMPOSE_DEV) exec backend bash

dev-manage:
	$(COMPOSE_DEV) exec backend python manage.py $(ARGS)

prod:
	$(COMPOSE_PROD) up -d

prod-down:
	$(COMPOSE_PROD) down

prod-logs:
	$(COMPOSE_PROD) logs -f

build:
	$(COMPOSE_PROD) build hostcraft

clean:
	$(COMPOSE_DEV) down -v
	$(COMPOSE_PROD) down -v

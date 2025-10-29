.PHONY: up smoke down logs clean

BASE ?= http://127.0.0.1:8088
H    ?= x-api-key: dev-123

up:
	@docker compose -f docker/docker-compose.edge.yml up -d --build

smoke:
	@./scripts/smoke.sh

.PHONY: up smoke down logs clean

BASE ?= http://127.0.0.1:8088
H    ?= x-api-key: dev-123

up:
	@docker compose -f docker/docker-compose.edge.yml up -d --build

smoke:
	@./scripts/smoke.sh

# run IOC export tests only
test-iocs:
	@export API_KEY=dev-123; \
	PYTHONPATH=$(PWD) pytest -v tests/test_iocs.py

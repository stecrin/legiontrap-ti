PROJECT := legiontrap-ti
COMPOSE_EDGE := docker/docker-compose.edge.yml
COMPOSE_CLOUD := docker/docker-compose.cloud.yml

.PHONY: up-edge up-cloud down logs fmt test seed

up-edge:
\tdocker compose -f $(COMPOSE_EDGE) up -d

up-cloud:
\tdocker compose -f $(COMPOSE_CLOUD) up -d

down:
\tdocker compose -f $(COMPOSE_EDGE) -f $(COMPOSE_CLOUD) down --remove-orphans

logs:
\tdocker compose -f $(COMPOSE_EDGE) logs -f --tail=200

fmt:
\t. .venv/bin/activate && black . && isort . && ruff check --fix .

test:
\t. .venv/bin/activate && pytest -q

seed:
\t. .venv/bin/activate && python scripts/seed.py

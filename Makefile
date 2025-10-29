.PHONY: up smoke down logs clean

BASE ?= http://127.0.0.1:8088
H    ?= x-api-key: dev-123

up:
	@docker compose -f docker/docker-compose.edge.yml up -d --build

smoke:
	@echo "Waiting for API..."
	@ok=0; for i in `seq 1 40`; do \
	  if curl -fsS --max-time 1 $(BASE)/api/health >/dev/null; then ok=1; break; fi; \
	  sleep 0.5; \
	done; \
	test "$$ok" = 1 || { echo "health: TIMEOUT"; exit 1; }
	@echo "health: OK"

	@code=$$(curl -s -o /dev/null -w "%{http_code}" $(BASE)/api/stats); \
	test "$$code" = "401" && echo "auth guard (no key): OK" || (echo "auth guard: FAIL"; exit 1)

	@curl -fsS -H "$(H)" $(BASE)/api/config  >/dev/null && echo "config: OK"
	@curl -fsS -H "$(H)" $(BASE)/api/stats   >/dev/null && echo "stats(empty ok or not): OK"

	# baseline total
	@curl -s -H "$(H)" $(BASE)/api/stats \
	  | python -c 'import sys,json;print(json.load(sys.stdin)["counts"]["total"])' > .smoke_before
	@echo "baseline total: $$(cat .smoke_before)"

	# ingest one event
	@curl -fsS -X POST $(BASE)/api/ingest -H "$(H)" -H 'Content-Type: application/json' \
	  -d '{"source":"cowrie","eventid":"cowrie.login.failed","username":"root","password":"test","src_ip":"203.0.113.45"}' >/dev/null && echo "ingest: OK"

	# wait until total >= before+1
	@ok=0; total=0; before=$$(cat .smoke_before); \
	for i in `seq 1 20`; do \
	  total=$$(curl -s -H "$(H)" $(BASE)/api/stats \
	    | python -c 'import sys,json;print(json.load(sys.stdin)["counts"]["total"])'); \
	  if [ "$$total" -ge $$((before+1)) ]; then ok=1; break; fi; \
	  sleep 0.25; \
	done; \
	test "$$ok" = 1 && echo "stats delta: OK (before $$before → now $$total)" || { \
	  echo "stats delta: FAIL (before $$before → now $$total)"; \
	  echo "----- /api/stats dump -----"; \
	  curl -s -H "$(H)" $(BASE)/api/stats | python -m json.tool || true; \
	  rm -f .smoke_before; \
	  exit 1; \
	}
	@rm -f .smoke_before

	# IOC checks
	@echo "Waiting for IOCs..."
	@ok=0; for i in `seq 1 20`; do \
	  curl -fsS -H "$(H)" $(BASE)/api/iocs/ufw.txt | grep -q '203.0.113.45' && ok=1 && break || true; \
	  sleep 0.25; \
	done; test "$$ok" = 1 && echo "ufw iocs: OK" || (echo "ufw iocs: missing IP"; exit 1)

	@ok=0; for i in `seq 1 20`; do \
	  curl -fsS -H "$(H)" $(BASE)/api/iocs/pf.conf | grep -q '203.0.113.45' && ok=1 && break || true; \
	  sleep 0.25; \
	done; test "$$ok" = 1 && echo "pf iocs: OK" || (echo "pf iocs: missing IP"; exit 1)

	@echo "ALL GOOD ✅"

down:
	@docker compose -f docker/docker-compose.edge.yml down

logs:
	@docker compose -f docker/docker-compose.edge.yml logs -f api

clean:
	@rm -f .smoke_before storage/events.jsonl
seed:
	@./scripts/seed_demo.sh

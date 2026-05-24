H ?= x-api-key: $(or $(API_KEY),dev-123)
PORT ?= 8088

run:
	UVICORN_LOOP=asyncio uvicorn app.main:app --port $(PORT) --log-level debug

ui:
	uv run fastapi dev app/main.py --port 8088

# ---------------------------------------------------------------------------
# Database lifecycle — operator-controlled, never automatic on app startup.
# Set DB_PATH in .env or the environment before running these targets.
# ---------------------------------------------------------------------------

# Apply all pending Alembic migrations. Run once after first deploy and after
# each new migration file is added.
db-migrate:
	alembic upgrade head

# Show the currently applied migration revision.
db-status:
	alembic current

# Roll back the most recent migration (one step). Use with caution in production.
db-rollback:
	alembic downgrade -1

# Show migration history with the current revision marked.
db-pending:
	alembic history --indicate-current

smoke:
	@echo "[health]"; curl -s http://127.0.0.1:$(PORT)/api/health | python3 -m json.tool
	@echo "[ingest]"; curl -s -H "$(H)" -H 'Content-Type: application/json' \
		-d '{"events":[{"ts":"2025-10-28T18:31:08+00:00","source":"cowrie","type":"cowrie.login.failed","data":{"ip":"203.0.113.2","username":"root","password":"bad"}}]}' \
		http://127.0.0.1:$(PORT)/api/ingest | python3 -m json.tool
	@echo "[stats]";  curl -s -H "$(H)" http://127.0.0.1:$(PORT)/api/stats | python3 -m json.tool
	@echo "[ufw]";    curl -s -H "$(H)" http://127.0.0.1:$(PORT)/api/iocs/ufw.txt
	@echo "[pf]";     curl -s -H "$(H)" http://127.0.0.1:$(PORT)/api/iocs/pf.conf

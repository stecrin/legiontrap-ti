H ?= x-api-key: $(or $(API_KEY),dev-123)
PORT ?= 8088

run:
	UVICORN_LOOP=asyncio uvicorn ui.backend.app.main:app --port $(PORT) --log-level debug

smoke:
	@echo "[health]"; curl -s http://127.0.0.1:$(PORT)/api/health | python3 -m json.tool
	@echo "[ingest]"; curl -s -H "$(H)" -H 'Content-Type: application/json' \
		-d '{"src_ip":"8.8.8.8","event_type":"cowrie.login"}' \
		http://127.0.0.1:$(PORT)/api/ingest | python3 -m json.tool
	@echo "[stats]";  curl -s -H "$(H)" http://127.0.0.1:$(PORT)/api/stats | python3 -m json.tool
	@echo "[iocs]";   curl -s -H "$(H)" http://127.0.0.1:$(PORT)/api/iocs.json | python3 -m json.tool
	@echo "[ufw]";    curl -s -H "$(H)" http://127.0.0.1:$(PORT)/api/iocs/ufw.txt
	@echo "[pf]";     curl -s -H "$(H)" http://127.0.0.1:$(PORT)/api/iocs/pf.conf
ui:
\tuv run fastapi dev app/main.py --port 8088

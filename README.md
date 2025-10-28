# LegionTrap TI
Modular, edge-ready honeynet with privacy-by-design, ATT&CK/Sigma exports, and a clean UI.

## Quick start (coming soon)
- `make up-edge` to run the lightweight profile.
- `make up-cloud` for the full stack on a server.

## Status
Initializing repository skeleton (Step 1).
## Quick start (local)

```bash
# start / rebuild
make up

# health (open route, no auth)
curl -s http://127.0.0.1:8088/api/health

# protected routes (require x-api-key)
H='x-api-key: dev-123'
curl -s -H "$H" http://127.0.0.1:8088/api/config | python -m json.tool
curl -s -H "$H" http://127.0.0.1:8088/api/stats  | python -m json.tool
curl -s -H "$H" http://127.0.0.1:8088/api/iocs/ufw.txt
curl -s -H "$H" http://127.0.0.1:8088/api/iocs/pf.conf

```

### Authentication
All non-health endpoints require the `x-api-key` header.
In local compose we set `API_KEY=dev-123` (see `docker/docker-compose.edge.yml`). Change it for your env.

### Negative test (bad key → 401)
```bash
curl -i -H 'x-api-key: wrong-key' http://127.0.0.1:8088/api/stats
# Expect: HTTP/1.1 401 Unauthorized



### Authentication
All non-health endpoints require the `x-api-key` header.
In local compose we set `API_KEY=dev-123` (see `docker/docker-compose.edge.yml`). Change it for your env.

### Negative test (bad key → 401)
```bash
curl -i -H 'x-api-key: wrong-key' http://127.0.0.1:8088/api/stats
# Expect: HTTP/1.1 401 Unauthorized

```  # closes the open ```bash fence above

### Privacy mode
Set `PRIVACY_MODE=on` to redact/limit personally identifying fields during normalization/exports.

Check current runtime config:
```bash
H='x-api-key: dev-123'
curl -s -H "$H" http://127.0.0.1:8088/api/config | python -m json.tool

```

```

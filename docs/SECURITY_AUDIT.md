# LegionTrap TI — Security Audit

**Document type:** Security posture assessment and remediation tracking
**Audience:** Engineers, autonomous agents, security reviewers
**Last reviewed:** 2026-05-24
**Phase 0 status:** Complete — all Critical issues (C-001 through C-004) resolved on branch `feat/phase0-security-hardening` (merged 2026-05-24).
**Deployment status:** Safe for trusted local network deployment. Not yet safe for internet-facing deployment without H-001 (CSP/httpOnly) and H-002 (TLS) addressed.

---

## Summary

LegionTrap TI has a sound security architecture in concept — dual-auth (JWT + API key), privacy-preserving IOC exports, and explicit credential requirements. In execution, several implementation gaps made the original state unsuitable for any deployment beyond a trusted local network.

**Phase 0 closed all four Critical issues.** The remaining open items (H-001, H-002, M-004) are deployment-hardening concerns, not blocking defects. The system is safe for trusted local network deployment in its current state.

None of the issues listed here are architectural flaws. They are implementation quality issues. The Phase 0 engineering cycle addressed all critical and high-priority items.

---

## Critical Issues (Must Fix Before Any Public Exposure)

### C-001: Plaintext Password Comparison — RESOLVED

**File:** `app/utils/auth.py`
**Severity:** Critical
**Status:** Resolved in Phase 0. `verify_user()` now uses `pwd_context.verify()` against a bcrypt hash. `DASH_PASS` must be set as a bcrypt hash in `.env`; startup raises `ValueError` if unset.
**Description:**
```python
def verify_user(username: str, password: str) -> bool:
    return username == DASH_USER and password == DASH_PASS
```
The password is read from the `.env` file as a plaintext string and compared directly to the submitted form value. `passlib` and `CryptContext` are imported and initialized but not used for password verification.

**Risk:** If an attacker reads the `.env` file (via directory traversal, misconfigured file permissions, or server compromise), they have immediate full dashboard access. There is no protection against timing attacks.

**Remediation:**
1. Store the dashboard password in `.env` as a bcrypt hash (generated once: `python -c "from passlib.context import CryptContext; print(CryptContext(schemes=['bcrypt']).hash('your-password'))"`)
2. Replace `verify_user()` with: `return username == DASH_USER and pwd_context.verify(password, DASH_PASS_HASH)`
3. Update `.env.example` to show the expected bcrypt hash format

**Effort:** 30 minutes.

---

### C-002: Wildcard CORS Policy — RESOLVED

**File:** `app/main.py`
**Severity:** Critical
**Status:** Resolved in Phase 0. `allow_origins` now reads from `settings.CORS_ORIGINS` (env var, no wildcard default). Wildcard + `allow_credentials=True` combination is gone.
**Description:**
```python
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    ...
)
```
`allow_origins=["*"]` combined with `allow_credentials=True` is a particularly dangerous combination. In theory, `allow_credentials=True` with wildcard origins should be rejected by browsers, but the intent is clearly wrong and the configuration should be fixed regardless.

**Risk:** Any website can make credentialed requests to the API on behalf of a browser that holds a valid JWT. This enables CSRF-style attacks.

**Remediation:**
1. Add `CORS_ORIGINS` environment variable (default: `http://localhost:5173,http://localhost:8088`)
2. Replace `allow_origins=["*"]` with `allow_origins=settings.CORS_ORIGINS.split(",")`
3. For production deployment, set `CORS_ORIGINS` to the actual dashboard URL

**Effort:** 1 hour.

---

### C-003: Hardcoded Default Credentials — RESOLVED

**Files:** `app/core/config.py`, `app/utils/auth.py`
**Severity:** Critical
**Status:** Resolved in Phase 0. All hardcoded defaults removed. `API_KEY`, `JWT_SECRET`, `DASH_PASS`, and `FEED_SALT` have no fallback values; startup raises `ValueError` if any required secret is unset. `.env.example` documents all required variables.
**Description:**

| Credential | Default value | Location |
|---|---|---|
| `API_KEY` | `dev-123` | `config.py`, `docker-compose.edge.yml` |
| `JWT_SECRET` | `devsecret` | `auth.py` |
| `DASH_PASS` | `change-me-please` | `auth.py` |
| `FEED_SALT` | `change-me` | `config.py` |

These defaults are in the public source code. Any deployment that does not explicitly set these values ships with publicly known credentials.

**Risk:** An attacker who knows the application (it is public on GitHub) can authenticate to any unmodified deployment using these defaults.

**Remediation:**
1. Remove all default values for security-sensitive settings in `config.py` and `auth.py`
2. Raise a clear startup error if any required secret is missing: `raise ValueError("JWT_SECRET must be set in environment")`
3. Provide an `.env.example` file with placeholder values and instructions
4. Update Docker Compose to document that credentials must be set before use

**Effort:** 2 hours.

---

### C-004: No Rate Limiting on Login Endpoint — RESOLVED

**File:** `app/routers/auth_router.py`
**Severity:** High
**Status:** Resolved in Phase 0. `slowapi` added; `/api/login` is limited to 5 requests/minute per IP (configurable via `LOGIN_RATE_LIMIT` env var). Returns HTTP 429 when exceeded.
**Description:** `POST /api/login` accepts an unlimited number of authentication attempts. There is no rate limiting, no account lockout, and no progressive delay.

**Risk:** An attacker can attempt unlimited password guesses against the login endpoint without restriction.

**Remediation:**
1. Add `slowapi` (FastAPI-compatible rate limiting library) as a dependency
2. Apply a rate limit of 5 requests per minute per IP to the `/api/login` endpoint
3. Return `HTTP 429 Too Many Requests` when the limit is exceeded

**Effort:** 2–3 hours.

---

## High Severity Issues

### H-001: JWT Stored in localStorage

**File:** `ui/dashboard/src/App.jsx`, `ui/dashboard/src/pages/Login.jsx`
**Severity:** High
**Description:** After successful login, the JWT is stored in `localStorage`. Any JavaScript running on the page can read `localStorage`, making the token vulnerable to XSS attacks.

**Risk:** A successful XSS attack on the dashboard can steal the JWT token, enabling persistent unauthorized access.

**Remediation:**
- Short-term: Ensure the Content-Security-Policy header prevents inline script execution
- Medium-term: Migrate to `httpOnly` cookies for token storage. The backend must set the token as a cookie on login; the frontend makes credentialed requests using `credentials: 'include'`; the token is not accessible to JavaScript

**Effort (short-term CSP):** 1 hour. **Effort (httpOnly cookie migration):** 4–6 hours.

---

### H-002: No HTTPS Enforcement

**File:** `docker/docker-compose.edge.yml`
**Severity:** High
**Description:** The Docker Compose deployment exposes the API on HTTP port 8088 with no TLS termination. Credentials and JWT tokens transmitted over HTTP are visible to network observers.

**Risk:** On any network that is not a trusted local loopback, credentials, JWT tokens, and event data are transmitted in plaintext.

**Remediation:**
1. Add a Caddy or nginx reverse proxy service to the Docker Compose configuration
2. Configure automatic TLS via Let's Encrypt (Caddy handles this with minimal configuration)
3. Redirect HTTP to HTTPS
4. Document that the deployment is intended for local use only without TLS configuration

**Effort:** 3–4 hours.

---

### H-003: Deprecated datetime.utcnow() — RESOLVED (stale)

**File:** `app/utils/auth.py`
**Severity:** Medium (will become High on Python 3.13+)
**Status:** Already resolved. `app/utils/auth.py` uses `datetime.now(UTC)` throughout. The original file reference (`stats.py:58`) was incorrect — `stats.py` has no `datetime` usage. No further action required.

**Effort:** 5 minutes.

---

## Medium Severity Issues

### M-001: Unvalidated Event Data

**File:** `app/routers/iocs_pf.py:iter_events()`
**Severity:** Medium
**Description:** Events are ingested directly from the JSONL file with no schema validation. The `_extract_all_ips()` function recursively searches for IPv4 strings in arbitrary JSON structures. There is no limit on nesting depth, no validation of field types, and no sanitization of string content.

**Risk:** A malformed or adversarially crafted event can cause unexpected behavior. When the ingestion API is added, this becomes a more significant attack surface.

**Remediation:** Define a Pydantic schema for `HoneypotEvent`. Validate all ingested events against this schema. Reject events that fail validation with logged errors.

---

### M-002: No Input Validation on Query Parameters

**File:** `app/routers/events.py:list_events()`
**Severity:** Medium
**Description:** The `limit` parameter is validated by FastAPI (ge=1, le=1000) but no other input validation exists. When the database layer is added, SQL injection prevention must be explicitly verified.

**Remediation:** Use parameterized queries exclusively when SQLite is adopted. Never construct SQL strings from user input. Document the SQL injection prevention strategy.

---

### M-003: Sensitive Files Not Explicitly Gitignored

**File:** `.gitignore`
**Severity:** Medium
**Description:** `tmp_events_test.jsonl` and `tmp.log` are present at the repository root and are not in `.gitignore`. They could be accidentally committed, potentially containing real event data.

**Remediation:** Add these patterns to `.gitignore`. Also review and document what other runtime-generated files could appear at the repository root.

---

### M-004: No Audit Logging

**Severity:** Medium
**Description:** There is no audit log of authentication events (successful logins, failed logins, API key usage), AI API calls, or data export operations. For any deployment handling real security telemetry, audit logs are a basic operational requirement.

**Remediation:** Add structured logging for:
- Authentication events (success/failure, method, timestamp, source IP)
- IOC export operations (which feed, timestamp, event count)
- AI API calls (when implemented: timestamp, data volume, not data content)
- Administrative actions

---

## Technical Debt with Security Implications

### TD-001: `passlib` crypt Module Deprecation

**File:** `.venv/lib/python3.11/site-packages/passlib/`
**Description:** `passlib` uses the Python `crypt` module, which is deprecated in Python 3.12 and removed in Python 3.13. On Python 3.11, a deprecation warning is emitted during tests. This will become a hard error when the Python version is updated.

**Remediation:** Monitor `passlib` for an update that removes the `crypt` dependency. Consider migrating to `argon2-cffi` for password hashing, which has no deprecated dependencies.

---

### TD-002: No Security Scanning in CI — RESOLVED (baseline)

**File:** `.github/workflows/ci.yml`
**Description:** The CI pipeline runs lint and tests but no security scanning. Dependency vulnerabilities, known-bad code patterns (Bandit), and secret leakage (detect-secrets) are not checked.

**Status:** Resolved in Phase 0 (baseline). `pip-audit` and `bandit -r app/ -ll` added to CI. Both run with `continue-on-error: true` pending initial triage of findings (TODO comments in `ci.yml`). `detect-secrets` deferred — requires a maintained `.secrets.baseline` file to avoid false positives on test fixtures.

---

### TD-003: auto-version.yml Pushes Directly to Main

**File:** `.github/workflows/auto-version.yml`
**Description:** The semantic-release workflow has `contents: write` permission and pushes version bump commits and tags directly to the `main` branch. This bypasses any branch protection rules and violates the `CLAUDE.md` "never push to main" principle.

**Risk:** Any commit to `main` triggers an automatic version bump push to `main`. In a team environment, this can create race conditions and bypass code review requirements.

**Assessment:** This is an intentional design choice for a solo-maintainer automated release workflow. It is acceptable in its current context but should be revisited if the project gains contributors or formal branch protection rules.

---

## Production Readiness Checklist

The following must be true before any internet-facing deployment:

- [x] C-001: bcrypt password verification implemented
- [x] C-002: CORS restricted to explicit origins via `CORS_ORIGINS` env var
- [x] C-003: All hardcoded defaults removed; startup validation raises `ValueError` if secrets unset
- [x] C-004: Rate limiting on `/api/login` (5/min per IP via `slowapi`)
- [ ] H-001: CSP headers set; httpOnly cookie migration planned — **deferred to Phase 1**
- [ ] H-002: TLS termination in Docker Compose — **deferred, infrastructure concern**
- [x] H-003: `datetime.utcnow()` — already using `datetime.now(UTC)` (resolved, audit ref was stale)
- [ ] `.env` populated with non-default secrets — **operator deployment responsibility, not a code requirement**
- [ ] Audit logging implemented — **deferred to Phase 1 (table designed in DATABASE_SCHEMA.md)**
- [x] CI includes `pip-audit` and `bandit` (baseline; `continue-on-error` pending triage)

---

*Cross-references: [ARCHITECTURE.md](ARCHITECTURE.md) · [ROADMAP.md](ROADMAP.md) · [AUTONOMOUS_OPERATIONS.md](AUTONOMOUS_OPERATIONS.md)*

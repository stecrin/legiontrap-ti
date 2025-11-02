# Changelog

All notable changes to this project will be documented in this file.

## [Unreleased]

## [0.1.0] - 2025-10-29
### Added
- Seed script: `scripts/seed_demo.sh` and `make seed`.
- README: Quick start, auth, privacy mode, smoke test.
- README: Environment configuration table.
- README: Events paging & time-filter examples.
- CI: GitHub Actions workflow (black, ruff, pytest).
- License: MIT.

### Changed
- Makefile: developer targets (up/logs/down/smoke/seed).

## [0.1.1] - 2025-11-02
### Added
- Finalized IOC export module (`iocs_pf.py`) with full test coverage (12/12 passing).
- Nested IP extraction for multiple keys (`src_ip`, `source_ip`, `ip`, `client_ip`, `remote_addr`).
- Privacy mode masking (`PRIVACY_MODE=on`) for safe IOC sharing.

### Changed
- Refactored pf.conf exporter with tempdir detection and file-readiness wait loop.
- Improved debug logging with file preview and size verification.
- Standardized imports and formatting (Black/isort/Ruff compliance).

### Fixed
- Resolved test path conflicts under pytest temporary directories.
- Eliminated false “# empty table” cases during IOC export.

### CI
- Pre-commit hooks: Black, isort, Ruff, whitespace trim.
- ✅ All pytest cases passing (`12/12`) on Python 3.13.

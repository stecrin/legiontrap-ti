import os
import pathlib


def pytest_sessionstart(session):
    # Ensure auth is enforced during tests
    os.environ.setdefault("API_KEY", "dev-123")

    # Create a writable storage dir and point EVENTS_PATH at it
    storage = pathlib.Path("./storage").resolve()
    storage.mkdir(parents=True, exist_ok=True)
    events_path = storage / "test-events.jsonl"
    os.environ["EVENTS_PATH"] = str(events_path)

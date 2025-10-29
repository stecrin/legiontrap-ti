"""Package export: `from app import app` gives the FastAPI instance."""

from .main import app as app

__all__ = ["app"]

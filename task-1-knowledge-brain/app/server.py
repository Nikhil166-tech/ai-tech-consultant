"""
ASGI entrypoint alias redirecting to app.main:app.
Permits running either:
  uvicorn app.main:app --port 8000 --reload
or:
  uvicorn app.server:app --port 8000 --reload
"""
from app.main import app

__all__ = ["app"]

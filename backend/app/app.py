"""Vercel FastAPI entry point.

Deploy the ``backend`` directory as its own Vercel project. Vercel recognises
``app/app.py`` and discovers the ASGI application exported here.
"""

from .main import app

__all__ = ["app"]

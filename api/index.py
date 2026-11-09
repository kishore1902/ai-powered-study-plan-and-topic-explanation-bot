"""Vercel entry point. Vercel looks for an ASGI app called `app` in api/index.py."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.main import app  # noqa: E402,F401

"""Vercel serverless entry point for SysmEasy FastAPI app."""
import sys
import os

# Ensure project root is on path
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from server import app  # noqa: F401 — Vercel picks up `app` as the ASGI handler

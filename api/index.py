"""Vercel Serverless Function entrypoint for MAELIN FastAPI application."""
import sys
from pathlib import Path

# Ensure project root is in sys.path
ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from maelin.api import api

# Vercel's Python runtime requires an ASGI/WSGI callable named 'app'
app = api

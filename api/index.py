"""Vercel's Flask entrypoint.

The application factory selects Neon PostgreSQL when DATABASE_URL is present.
"""
from app import create_app

app = create_app()

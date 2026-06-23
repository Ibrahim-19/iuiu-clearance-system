"""Manual/local CLI entry point for seeding.

On Render, this runs automatically on every app boot (see app/__init__.py)
since the free tier has no shell access to run this script after deploy.
This file is kept for local development convenience:

    python seed.py
"""
from app import create_app
from app.seed_data import run_seed

app = create_app()

if __name__ == "__main__":
    with app.app_context():
        run_seed()
        print("\nDone. (This also runs automatically on every app startup.)")

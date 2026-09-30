"""Production entry point: gunicorn wsgi:app (see Dockerfile).

Run a single gunicorn worker (with threads): renders, uploads and progress live in the
process's memory, so a second worker wouldn't see them.
"""
from backend import cleanup, create_app

app = create_app()
cleanup.start_scheduler(app)  # auto-clean of posted videos, if the admin turned it on

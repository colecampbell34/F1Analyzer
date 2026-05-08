"""Vercel WSGI entrypoint.

The local app keeps using `python app.py`. Vercel imports this module and
serves the Flask WSGI object exposed as `app`.
"""

from app import server as app

"""Starts the moto server with Werkzeug's per-request access log quieted down.

moto_server has no --log-level flag of its own; the request-per-line noise
comes from Werkzeug's dev server, so this calls moto's own entrypoint
directly after lowering the werkzeug logger below its default INFO.
"""
import logging

from moto.server import main

logging.getLogger("werkzeug").setLevel(logging.WARNING)

if __name__ == "__main__":
    main(["-H", "0.0.0.0", "-p", "5001", "-c", "certs/cert.pem", "-k", "certs/key.pem"])

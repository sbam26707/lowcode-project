"""Application factory."""
from __future__ import annotations

import os
import secrets

from flask import Flask, redirect, url_for

from .contact import bp as contact_bp
from .security import init_csrf


def create_app(test_config: dict | None = None) -> Flask:
    app = Flask(__name__)

    app.config.from_mapping(
        SECRET_KEY=os.environ.get("SECRET_KEY"),
        # Reject oversized request bodies before they are parsed (64 KB).
        MAX_CONTENT_LENGTH=64 * 1024,
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        # Set SESSION_COOKIE_SECURE=1 in production (HTTPS only).
        SESSION_COOKIE_SECURE=os.environ.get("SESSION_COOKIE_SECURE") == "1",
    )
    if test_config:
        app.config.from_mapping(test_config)

    if not app.config["SECRET_KEY"]:
        # Fine for local development. In production set SECRET_KEY, otherwise
        # sessions and CSRF tokens break across restarts and worker processes.
        app.config["SECRET_KEY"] = secrets.token_hex(32)
        app.logger.warning("SECRET_KEY is not set; using a temporary random key.")

    init_csrf(app)
    app.register_blueprint(contact_bp)

    @app.after_request
    def set_security_headers(response):
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "same-origin")
        response.headers.setdefault(
            "Content-Security-Policy",
            "default-src 'self'; form-action 'self'; frame-ancestors 'none'",
        )
        return response

    # Placeholder home page so the demo has an entry point. Remove this if your
    # existing app already defines "/".
    @app.get("/")
    def index():
        return redirect(url_for("contact.form"))

    return app

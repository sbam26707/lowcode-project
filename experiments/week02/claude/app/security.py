"""Minimal, dependency-free CSRF protection.

A random token is stored in the signed session cookie and must be echoed back
in every state-changing request, either as the ``csrf_token`` form field or the
``X-CSRFToken`` header. If the project later adopts Flask-WTF, this module can
be replaced by ``CSRFProtect(app)`` with no template changes beyond the hidden
field.
"""
from __future__ import annotations

import hmac
import secrets

from flask import Flask, render_template, request, session
from werkzeug.exceptions import BadRequest

CSRF_SESSION_KEY = "_csrf_token"
CSRF_FIELD_NAME = "csrf_token"
CSRF_HEADER_NAME = "X-CSRFToken"
_SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS", "TRACE"})


class CSRFError(BadRequest):
    description = "The form has expired or is invalid. Please reload the page and try again."


def generate_csrf_token() -> str:
    token = session.get(CSRF_SESSION_KEY)
    if not token:
        token = secrets.token_urlsafe(32)
        session[CSRF_SESSION_KEY] = token
    return token


def init_csrf(app: Flask) -> None:
    app.jinja_env.globals["csrf_token"] = generate_csrf_token

    @app.before_request
    def protect_against_csrf():
        if request.method in _SAFE_METHODS:
            return
        expected = session.get(CSRF_SESSION_KEY)
        supplied = request.form.get(CSRF_FIELD_NAME) or request.headers.get(CSRF_HEADER_NAME, "")
        # compare_digest needs bytes to accept non-ASCII input safely.
        if not expected or not supplied or not hmac.compare_digest(
            expected.encode(), supplied.encode()
        ):
            raise CSRFError()

    @app.errorhandler(CSRFError)
    def handle_csrf_error(error):
        return render_template("errors/csrf.html", message=error.description), 400

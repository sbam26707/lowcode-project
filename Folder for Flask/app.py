"""Hello app with a contact form at /contact."""
import hmac
import os
import secrets

from flask import Flask, redirect, render_template, request, session, url_for
from werkzeug.exceptions import BadRequest

from contact_validation import validate_contact_form

app = Flask(__name__)

app.config.update(
    # Set SECRET_KEY in your environment for anything beyond local testing.
    # The random fallback changes on every restart, which invalidates open forms.
    SECRET_KEY=os.environ.get("SECRET_KEY") or secrets.token_hex(32),
    # Reject request bodies larger than 64 KB before they are parsed.
    MAX_CONTENT_LENGTH=64 * 1024,
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
)
if not os.environ.get("SECRET_KEY"):
    app.logger.warning("SECRET_KEY is not set; using a temporary random key.")


# --- CSRF protection --------------------------------------------------------
# A random token lives in the signed session cookie and must come back with
# every POST, either as the hidden "csrf_token" field or an X-CSRFToken header.


class CSRFError(BadRequest):
    description = "The form has expired or is invalid. Please reload the page and try again."


def csrf_token() -> str:
    token = session.get("_csrf_token")
    if not token:
        token = secrets.token_urlsafe(32)
        session["_csrf_token"] = token
    return token


app.jinja_env.globals["csrf_token"] = csrf_token


@app.before_request
def check_csrf():
    if request.method in ("GET", "HEAD", "OPTIONS", "TRACE"):
        return
    expected = session.get("_csrf_token")
    supplied = request.form.get("csrf_token") or request.headers.get("X-CSRFToken", "")
    # compare_digest needs bytes to accept non-ASCII input safely.
    if not expected or not supplied or not hmac.compare_digest(expected.encode(), supplied.encode()):
        raise CSRFError()


@app.errorhandler(CSRFError)
def handle_csrf_error(error):
    return render_template("csrf_error.html", message=error.description), 400


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


# --- Existing page (unchanged) ----------------------------------------------


@app.route("/")
def index():
    return """<!doctype html>
<html lang="en">
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>Hello</title>
</head>
<body>
    <h1>Hello from Tim Hinchion</h1>
</body>
</html>"""


# --- Contact form -----------------------------------------------------------


def deliver_message(data: dict[str, str]) -> None:
    """Single hook for what happens to a valid submission.

    For now it only logs. Replace the body with an email send, database insert
    or queue publish. ``%r`` escapes newlines so user input cannot forge log
    lines. This logs personal data, so remove it once real delivery exists.
    """
    app.logger.info(
        "Contact message received: name=%r email=%r message=%r",
        data["name"],
        data["email"],
        data["message"],
    )


@app.route("/contact", methods=["GET", "POST"])
def contact():
    if request.method == "GET":
        return render_template("contact.html", values={}, errors={})

    result = validate_contact_form(request.form)
    if not result.is_valid:
        # Re-render with the submitted values and per-field errors.
        return render_template("contact.html", values=result.values, errors=result.errors), 400

    deliver_message(result.cleaned)

    # Post/Redirect/Get: a browser refresh cannot resubmit the form.
    session["contact_submitted_name"] = result.cleaned["name"]
    return redirect(url_for("thanks"))


@app.get("/contact/thanks")
def thanks():
    name = session.pop("contact_submitted_name", None)
    if name is None:
        # Nobody has just submitted; don't show a confirmation out of nowhere.
        return redirect(url_for("contact"))
    return render_template("thanks.html", name=name)


if __name__ == "__main__":
    app.run(debug=True)

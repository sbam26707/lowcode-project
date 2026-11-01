from __future__ import annotations

from flask import Blueprint, current_app, redirect, render_template, request, session, url_for

from .validation import validate_contact_form

bp = Blueprint("contact", __name__, url_prefix="/contact")

_SUBMITTED_KEY = "contact_submitted_name"


def deliver_message(data: dict[str, str]) -> None:
    """Single hook for what happens to a valid submission.

    Currently it only logs. Replace the body with an email send, database
    insert or queue publish. ``%r`` escapes newlines so user input cannot forge
    log lines. Note that this logs personal data; remove or redact it once real
    delivery exists.
    """
    current_app.logger.info(
        "Contact message received: name=%r email=%r message=%r",
        data["name"],
        data["email"],
        data["message"],
    )


@bp.route("", methods=["GET", "POST"])
def form():
    if request.method == "GET":
        return render_template("contact/form.html", values={}, errors={})

    result = validate_contact_form(request.form)
    if not result.is_valid:
        # Re-render with the submitted values and per-field errors.
        return render_template("contact/form.html", values=result.values, errors=result.errors), 422

    deliver_message(result.cleaned)

    # Post/Redirect/Get: a browser refresh cannot resubmit the form.
    session[_SUBMITTED_KEY] = result.cleaned["name"]
    return redirect(url_for("contact.thanks"))


@bp.get("/thanks")
def thanks():
    name = session.pop(_SUBMITTED_KEY, None)
    if name is None:
        # Nobody has just submitted; don't show a confirmation out of nowhere.
        return redirect(url_for("contact.form"))
    return render_template("contact/thanks.html", name=name)

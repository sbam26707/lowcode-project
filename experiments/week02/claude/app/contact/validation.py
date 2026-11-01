"""Server-side validation for the contact form.

Pure Python with no Flask imports, so it is trivial to unit test and reuse.
"""
from __future__ import annotations

import re
import unicodedata
from collections.abc import Mapping
from dataclasses import dataclass

NAME_MAX_LENGTH = 100
EMAIL_MAX_LENGTH = 254  # RFC 5321 path limit
EMAIL_LOCAL_MAX_LENGTH = 64
MESSAGE_MAX_LENGTH = 5000

FIELDS = ("name", "email", "message")

# Pragmatic address check: dot-atom local part, then a domain of at least two
# DNS labels. Matched with fullmatch(), never "$", which would accept a
# trailing newline.
_EMAIL_RE = re.compile(
    r"[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+"
    r"@"
    r"(?:[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?\.)+"
    r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?"
)

# Control characters, plus the Unicode line/paragraph separators, are never
# valid in single-line fields (and block header-injection tricks if the values
# are later used in an email).
_FORBIDDEN_SINGLE_LINE = {"Cc", "Zl", "Zp"}


@dataclass(frozen=True)
class ContactFormResult:
    values: dict[str, str]   # exactly what the user submitted, for re-display
    cleaned: dict[str, str]  # trimmed/normalised values, safe to act on if valid
    errors: dict[str, str]   # field name -> message

    @property
    def is_valid(self) -> bool:
        return not self.errors


def _has_forbidden_chars(value: str, *, multiline: bool = False) -> bool:
    for ch in value:
        if multiline and ch in "\n\r\t":
            continue
        if unicodedata.category(ch) in _FORBIDDEN_SINGLE_LINE:
            return True
    return False


def _is_valid_email(address: str) -> bool:
    if len(address) > EMAIL_MAX_LENGTH or not _EMAIL_RE.fullmatch(address):
        return False
    local, _, domain = address.rpartition("@")
    if len(local) > EMAIL_LOCAL_MAX_LENGTH:
        return False
    if local.startswith(".") or local.endswith(".") or ".." in local:
        return False
    if domain.rsplit(".", 1)[1].isdigit():  # all-numeric TLD, e.g. user@1.2.3.4
        return False
    return True


def validate_contact_form(form: Mapping[str, str]) -> ContactFormResult:
    values = {field: str(form.get(field, "")) for field in FIELDS}
    errors: dict[str, str] = {}

    # Name
    name = values["name"].strip()
    if not name:
        errors["name"] = "Please enter your name."
    elif len(name) > NAME_MAX_LENGTH:
        errors["name"] = f"Your name must be {NAME_MAX_LENGTH} characters or fewer."
    elif _has_forbidden_chars(name):
        errors["name"] = "Your name contains characters that are not allowed."

    # Email
    email = values["email"].strip()
    if not email:
        errors["email"] = "Please enter your email address."
    elif not _is_valid_email(email):
        errors["email"] = "Please enter a valid email address, like name@example.com."

    # Message (normalise line endings so length checks match what we store)
    message = values["message"].replace("\r\n", "\n").replace("\r", "\n").strip()
    if not message:
        errors["message"] = "Please enter a message."
    elif len(message) > MESSAGE_MAX_LENGTH:
        errors["message"] = f"Your message must be {MESSAGE_MAX_LENGTH} characters or fewer."
    elif _has_forbidden_chars(message, multiline=True):
        errors["message"] = "Your message contains characters that are not allowed."

    cleaned = {"name": name, "email": email, "message": message}
    return ContactFormResult(values=values, cleaned=cleaned, errors=errors)

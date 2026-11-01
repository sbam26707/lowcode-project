# Week 2 — AI Tool Comparison

## The requirement

Add a contact form at `/contact` to a Flask application. It must validate name, email and
message on the server (not only in the browser), reject empty fields and a malformed email
address, re-render the form with the user's values and clear error messages on failure, and
show a confirmation on success. No storage yet.

## Prompts used

### Tool 1: Claude (Sonnet 5.5)

```
You are a senior Python and Flask engineer.
TASK
Add a contact form to an existing Flask application.
SPECIFICITY
- Language: Python 3.11
- Framework: Flask
- Feature: Contact Form
- Route: /contact
- Fields:
  - name
  - email
  - message
REQUIREMENTS
1. Create a page that renders at /contact.
2. Display a form containing name, email, and message fields.
3. Validate all inputs on the server side.
4. Reject empty name fields and display a visible validation error.
5. Reject empty message fields and display a visible validation error.
6. Validate that the email address is properly formatted on the server side.
7. If validation fails, re-render the form with the user's entered values and clear error messages.
8. On successful submission, show a confirmation page indicating the message was received.
CONSTRAINTS
- Use Flask best practices.
- Use Python 3.11 compatible code.
- Do not rely solely on HTML5 browser validation.
- Server-side validation is mandatory.
- Do not introduce unnecessary dependencies unless they provide significant value.
- Preserve existing application structure where possible.
- Produce secure code that handles user input safely.
CONTEXT
Assume this feature is being added to an existing Flask application.
Review the current project structure before making changes.
Identify all files that need to be modified or created.
DELIVERABLES
Provide:
1. A summary of the implementation approach.
2. A list of files created or modified.
3. Complete code for each new or modified file.
4. Template HTML for:
   - contact form page
   - confirmation page
5. Explanation of the validation logic.
6. Instructions for running and testing the feature.
ITERATION RULES
If any project details are missing:
- First explain what assumptions you are making.
- Minimise assumptions where possible.
- If multiple approaches are possible, recommend the most maintainable Flask solution and explain why.
- Highlight any security, validation, or usability improvements that could be added in a future iteration.
```

### Tool 2: Claude (Sonnet 5.5), one-line prompt

Run in a fresh agent with no earlier conversation, so it could not reuse anything from Tool 1.
The only text it received was the prompt below plus a logistics line saying where to save files.

```
Add a contact form at /contact to my Flask app.
```

Logistics line added after it (not part of the prompt strategy): put every file under
`experiments/week02/claude-oneline/`, Flask 3.x is installed, no other packages can be installed.

## Scores


| Criterion | Tool 1 (structured prompt) | Tool 2 (one-line prompt) |
|---|---|---|
| Correctness | 5/5 | 4/5 |
| Code quality | 4/5 | 4/5 |
| Completeness | 5/5 | 3/5 |
| Security | 5/5 | 2/5 |

### Evidence for Tool 1 (Claude)

- **Correctness:** ran unmodified once the files were in the right folder. Empty form, `notanemail`,
  and a POST with no browser checks all returned HTTP 422 with an error shown for each bad field.
  A valid submission redirected (302) to `/contact/thanks`. A 22-test suite passed.
- **Code quality:** validation is in its own pure-Python module (`app/contact/validation.py`,
  98 lines) with one small function per concern, separate from the route (`routes.py`, 51 lines).
  Downside: about 258 lines across 5 files for a simple form, which is more than the task needs.
- **Completeness:** handles empty fields, whitespace-only input, length limits, control
  characters, a bad email, and re-renders with the user's values. Also adds CSRF protection and a
  Post/Redirect/Get confirmation. No storage, as specified.
- **Security:** no `debug=True`, no hardcoded secret (`SECRET_KEY` is read from the environment,
  with a random fallback for local use). Output is escaped: `<script>alert(1)</script>` in the
  message came back as `&lt;script&gt;...` and the raw tag did not appear in the page. CSRF token
  and a 64 KB request-size limit are included. No packages beyond Flask.

### Evidence for Tool 2 (one-line prompt)


- **Correctness:** ran unmodified (`python app.py`). Empty form, `notanemail`, and a POST with
  no fields all rejected with the right messages. Valid input redirected (302) and showed the
  confirmation. But rejected submissions return HTTP **200**, not 400.
- **Code quality:** compact and readable: 35 lines in `app.py` plus one template, one route
  function. Everything is in one place; a reader sees all the logic at once.
- **Completeness:** only the happy path plus basic checks. No length limits (a 200 KB message
  was accepted), no control-character checks (`"Tim\nBcc: x@y.com"` was accepted as a name), and the
  email pattern accepts `a@b..c`. It also invented a 10-character minimum on messages that the prompt
  never asked for (a 5-character message was rejected).
- **Security:** `app.secret_key = "dev-secret-change-me"` is hardcoded (line 5) and
  `app.run(debug=True)` is on (line 35). No CSRF protection. Output is escaped (script text
  came back as `&lt;script&gt;`), thanks to Jinja2's default autoescaping. The full form is
  logged, which puts personal data in logs.

### Break tests: both versions side by side

| # | Test | Tool 1 (structured) | Tool 2 (one-line) |
|---|---|---|---|
| 1 | Empty form | 3 errors, HTTP 422 | 3 errors, HTTP 200 |
| 2 | `notanemail` | Rejected | Rejected |
| 3 | Browser checks removed | Still rejected | Still rejected |
| 4 | `<script>alert(1)</script>` | Escaped | Escaped |

## Break tests (run in the browser, Tool 1 / Claude)

| # | Test | Result |
|---|---|---|
| 1 | Submit the form completely empty | Errors shown for all three fields. |
| 2 | `notanemail` in the email field | Rejected: "Please enter a valid email address, like name@example.com." |
| 3 | DevTools: delete the `required` attribute from all three inputs, submit empty | Errors still appeared, so validation is on the server, not just in the browser. |
| 4 | `<script>alert(1)</script>` in the message field | Nothing happened: no pop-up, the text re-appeared as plain text. Page source shows it escaped as `&lt;script&gt;`. |

**Analysis:** Test 3 is the important one. A browser-only check would have failed it, and the
generated form passed because the checks run in Flask (`app/contact/validation.py`). Test 4 passing
is credit to Jinja2, not the AI: it escapes `{{ value }}` by default, so the framework protected
the output, not the generated code. (To verify this yourself: right-click the page, View page
source, search for `script`.)

## What each got wrong

**Tool 1 (Claude):**
- Returns HTTP **422** on validation failure; the course brief asks for **400**. My prompt did not
  ask for a status code, so this is a gap in my prompt rather than only the tool.
- Over-engineered for the size of the task: blueprint, app factory, custom CSRF module, session-based
  confirmation. A single `app.py` and two templates would do. This makes it harder to merge into
  an existing simple app.
- Did not use the file layout the course expects (`templates/contact.html` and the route in
  `app.py`), again because my prompt did not state it.
- The first draft of `app/security.py` contained a pointless leftover line (an
  `abort(...) if False else None` expression). It was removed before the first test run, but it
  shows the generated code needed a review pass.

**Tool 2 (one-line prompt):**
- `app.py` line 5: hardcoded `secret_key = "dev-secret-change-me"`. Anyone with the source can forge session cookies.
- `app.py` line 35: `debug=True`, which exposes the interactive debugger if run as written on a server.
- `app.py` line 7: email regex `^[^@\s]+@[^@\s]+\.[^@\s]+$` accepts `a@b..c`.
- `app.py` lines 20–26: no maximum length on any field; no control-character check.
- `app.py` line 25: invented a 10-character minimum for messages that the prompt did not ask for.
- `app.py` lines 29–30: confirmation is a flash message on the form page, not a separate confirmation page.
- Validation failures return HTTP 200 rather than 400.
- No CSRF protection.

## Which I kept, and why

I kept Tool 1 (the structured prompt output). The deciding criterion was Security: the
one-line version hardcoded `secret_key = "dev-secret-change-me"` (line 5), ran with
`debug=True` (line 35) and had no CSRF protection, while the structured version read its
secret from the environment and rejected forged requests. Completeness also favoured it,
since it enforced length limits and rejected control characters that the one-line version
accepted. The trade-off was size: it needed about 258 lines against 67, and I had to reshape
it to fit my single-file app. I judged that cost worth paying for the security gain.

from flask import Flask, render_template, request, redirect, url_for, flash
import re

app = Flask(__name__)
app.secret_key = "dev-secret-change-me"

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


@app.route("/")
def index():
    return redirect(url_for("contact"))


@app.route("/contact", methods=["GET", "POST"])
def contact():
    form = {"name": "", "email": "", "message": ""}
    errors = {}
    if request.method == "POST":
        form = {k: request.form.get(k, "").strip() for k in form}
        if not form["name"]:
            errors["name"] = "Please enter your name."
        if not EMAIL_RE.match(form["email"]):
            errors["email"] = "Please enter a valid email address."
        if len(form["message"]) < 10:
            errors["message"] = "Message must be at least 10 characters."
        if not errors:
            app.logger.info("Contact form: %s", form)
            flash("Thanks, your message has been sent!")
            return redirect(url_for("contact"))
    return render_template("contact.html", form=form, errors=errors)


if __name__ == "__main__":
    app.run(debug=True)

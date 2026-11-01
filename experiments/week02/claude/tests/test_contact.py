import re
import unittest

from app import create_app
from app.contact.validation import validate_contact_form

VALID = {"name": "Ada Lovelace", "email": "ada@example.com", "message": "Hello there"}


class ContactRouteTests(unittest.TestCase):
    def setUp(self):
        self.app = create_app({"TESTING": True, "SECRET_KEY": "test"})
        self.client = self.app.test_client()

    def token(self):
        html = self.client.get("/contact").get_data(as_text=True)
        return re.search(r'name="csrf_token" value="([^"]+)"', html).group(1)

    def post(self, **overrides):
        data = {**VALID, **overrides, "csrf_token": self.token()}
        return self.client.post("/contact", data=data)

    # --- rendering -------------------------------------------------------
    def test_get_renders_form(self):
        resp = self.client.get("/contact")
        self.assertEqual(resp.status_code, 200)
        html = resp.get_data(as_text=True)
        for field in ("name", "email", "message"):
            self.assertIn(f'name="{field}"', html)

    # --- required fields -------------------------------------------------
    def test_empty_name_rejected(self):
        resp = self.post(name="")
        self.assertEqual(resp.status_code, 422)
        self.assertIn("Please enter your name.", resp.get_data(as_text=True))

    def test_whitespace_only_name_rejected(self):
        resp = self.post(name="   ")
        self.assertIn("Please enter your name.", resp.get_data(as_text=True))

    def test_empty_message_rejected(self):
        resp = self.post(message="")
        self.assertEqual(resp.status_code, 422)
        self.assertIn("Please enter a message.", resp.get_data(as_text=True))

    def test_invalid_email_rejected(self):
        resp = self.post(email="not-an-email")
        self.assertEqual(resp.status_code, 422)
        self.assertIn("valid email address", resp.get_data(as_text=True))

    def test_all_errors_shown_together(self):
        resp = self.post(name="", email="bad", message="")
        html = resp.get_data(as_text=True)
        self.assertIn("Please enter your name.", html)
        self.assertIn("valid email address", html)
        self.assertIn("Please enter a message.", html)

    # --- re-rendering ----------------------------------------------------
    def test_values_preserved_on_error(self):
        resp = self.post(name="", email="keep@example.com", message="Keep this text")
        html = resp.get_data(as_text=True)
        self.assertIn('value="keep@example.com"', html)
        self.assertIn("Keep this text</textarea>", html)

    def test_user_input_is_escaped(self):
        resp = self.post(name="<script>alert(1)</script>", email="bad")
        html = resp.get_data(as_text=True)
        self.assertNotIn("<script>alert(1)</script>", html)
        self.assertIn("&lt;script&gt;alert(1)&lt;/script&gt;", html)

    # --- success flow ----------------------------------------------------
    def test_success_redirects_to_confirmation(self):
        resp = self.post()
        self.assertEqual(resp.status_code, 302)
        self.assertTrue(resp.headers["Location"].endswith("/contact/thanks"))
        page = self.client.get("/contact/thanks")
        self.assertEqual(page.status_code, 200)
        html = page.get_data(as_text=True)
        self.assertIn("Your message has been received", html)
        self.assertIn("Ada Lovelace", html)

    def test_confirmation_not_repeatable(self):
        self.post()
        self.client.get("/contact/thanks")
        again = self.client.get("/contact/thanks")
        self.assertEqual(again.status_code, 302)

    def test_confirmation_without_submission_redirects(self):
        resp = self.client.get("/contact/thanks")
        self.assertEqual(resp.status_code, 302)
        self.assertTrue(resp.headers["Location"].endswith("/contact"))

    # --- CSRF ------------------------------------------------------------
    def test_missing_csrf_token_rejected(self):
        self.client.get("/contact")
        resp = self.client.post("/contact", data=VALID)
        self.assertEqual(resp.status_code, 400)

    def test_wrong_csrf_token_rejected(self):
        self.client.get("/contact")
        resp = self.client.post("/contact", data={**VALID, "csrf_token": "forged"})
        self.assertEqual(resp.status_code, 400)

    def test_non_ascii_csrf_token_does_not_crash(self):
        self.client.get("/contact")
        resp = self.client.post("/contact", data={**VALID, "csrf_token": "ünï"})
        self.assertEqual(resp.status_code, 400)

    def test_oversized_body_rejected(self):
        resp = self.post(message="x" * (70 * 1024))
        self.assertEqual(resp.status_code, 413)


class ValidationTests(unittest.TestCase):
    def check(self, **overrides):
        return validate_contact_form({**VALID, **overrides})

    def test_valid_submission(self):
        result = self.check()
        self.assertTrue(result.is_valid)
        self.assertEqual(result.cleaned, VALID)

    def test_values_are_trimmed_and_newlines_normalised(self):
        result = self.check(name="  Ada  ", message="a\r\nb\rc  ")
        self.assertEqual(result.cleaned["name"], "Ada")
        self.assertEqual(result.cleaned["message"], "a\nb\nc")
        # Surrounding whitespace (including a trailing newline) is trimmed before validation.
        self.assertEqual(self.check(email=" a@example.com\n").cleaned["email"], "a@example.com")

    def test_valid_emails(self):
        for email in ("a@example.com", "first.last+tag@sub.example.co.uk", "o'brien@example.ie"):
            with self.subTest(email=email):
                self.assertNotIn("email", self.check(email=email).errors)

    def test_invalid_emails(self):
        bad = [
            "", "plainaddress", "a@b", "a@@b.com", "a b@example.com", "@example.com",
            "a@", "a@.com", "a@example..com", ".a@example.com", "a.@example.com",
            "a..b@example.com", "a@-example.com", "a@example-.com", "user@1.2.3.4",
            "a@example.com\nBcc: evil@example.com", "x" * 250 + "@example.com",
        ]
        for email in bad:
            with self.subTest(email=email):
                self.assertIn("email", self.check(email=email).errors)

    def test_length_limits(self):
        self.assertIn("name", self.check(name="n" * 101).errors)
        self.assertNotIn("name", self.check(name="n" * 100).errors)
        self.assertIn("message", self.check(message="m" * 5001).errors)
        self.assertNotIn("message", self.check(message="m" * 5000).errors)

    def test_control_characters_rejected(self):
        self.assertIn("name", self.check(name="Ada\nLovelace").errors)
        self.assertIn("name", self.check(name="Ada\x00").errors)
        self.assertIn("name", self.check(name="Ada Lovelace").errors)
        self.assertIn("message", self.check(message="hi\x00there").errors)
        # Ordinary newlines and tabs are fine in a message.
        self.assertNotIn("message", self.check(message="line1\n\tline2").errors)

    def test_missing_fields_treated_as_empty(self):
        result = validate_contact_form({})
        self.assertEqual(set(result.errors), {"name", "email", "message"})


if __name__ == "__main__":
    unittest.main()

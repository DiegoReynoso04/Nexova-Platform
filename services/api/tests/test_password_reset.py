"""AUTH-03: recuperación (forgot/reset) y cambio de contraseña, envío con Resend y auditoría.

Ningún test llama a Resend: el sender real se prueba construyendo la petición
y simulando `urlopen`; el resto usa un sender falso en `app.state.email_sender`.
"""

import dataclasses
import io
import json
import unittest
import urllib.error
from datetime import UTC, datetime, timedelta
from typing import Any
from unittest import mock
from urllib.parse import parse_qs, urlsplit

from app.auth.email import (
    RESEND_EMAILS_URL,
    DisabledEmailSender,
    EmailDeliveryError,
    EmailMessage,
    ResendEmailSender,
    password_reset_message,
    reset_link,
)
from app.auth.security import hash_reset_token
from app.core.config import ConfigError, Settings
from app.main import build_email_sender

from .auth_support import AuthTestCase, bearer, new_password
from .support import capture_logs

FORGOT_URL = "/auth/forgot-password"
RESET_URL = "/auth/reset-password"
CHANGE_URL = "/auth/change-password"
RESET_PAGE = "http://localhost:3000/reset-password"
ALICE = "alice@example.invalid"
NOBODY = "nobody@example.invalid"


class FakeEmailSender:
    def __init__(self, error: Exception | None = None) -> None:
        self.messages: list[EmailMessage] = []
        self.error = error

    def send(self, message: EmailMessage) -> None:
        if self.error is not None:
            raise self.error
        self.messages.append(message)


class FakeClock:
    def __init__(self) -> None:
        self.now = datetime(2026, 10, 6, 9, 0, tzinfo=UTC)

    def __call__(self) -> datetime:
        return self.now

    def advance(self, **delta: float) -> None:
        self.now += timedelta(**delta)


class PasswordTestCase(AuthTestCase):
    """App real con base temporal, sender falso y reloj controlado."""

    def setUp(self) -> None:
        super().setUp()
        self.sender = FakeEmailSender()
        self.app.state.email_sender = self.sender
        self.clock = FakeClock()
        self.service.repository._clock = self.clock
        # Configuración de email ficticia: el envío lo hace el sender falso.
        self.settings = dataclasses.replace(
            self.settings,
            resend_api_key="re_fake_test_key",
            email_from="Nexova <noreply@example.invalid>",
            password_reset_url=RESET_PAGE,
        )
        self.app.state.settings = self.settings

    def forgot(self, email: str) -> Any:
        return self.client.post(FORGOT_URL, json={"email": email})

    def reset(self, token: str, password: str) -> Any:
        return self.client.post(RESET_URL, json={"token": token, "new_password": password})

    def token_from_last_email(self) -> str:
        link = next(line for line in self.sender.messages[-1].text.splitlines() if line.startswith("http"))
        self.assertTrue(link.startswith(f"{RESET_PAGE}?token="), link)
        [token] = parse_qs(urlsplit(link).query)["token"]
        return token

    def requested_token(self, email: str = ALICE) -> str:
        self.assertEqual(self.forgot(email).status_code, 200)
        return self.token_from_last_email()

    def raw_table(self, name: str) -> list[dict[str, Any]]:
        return list(self.raw_db().get(name, {}).values())

    def assertInvalidToken(self, response: Any) -> None:
        self.assertEqual(response.status_code, 400, response.text)
        self.assertEqual(response.json()["code"], "invalid_reset_token")


class ForgotPasswordTests(PasswordTestCase):
    def test_registered_email_receives_a_reset_link(self) -> None:
        self.create_user(ALICE)
        response = self.forgot(ALICE)
        self.assertEqual(response.status_code, 200, response.text)
        [message] = self.sender.messages
        self.assertEqual(message.to, ALICE)
        self.assertIn("30 minutos", message.text)
        self.assertTrue(self.token_from_last_email())

    def test_unknown_email_gets_the_same_response_and_no_email(self) -> None:
        self.create_user(ALICE)
        known = self.forgot(ALICE)
        unknown = self.forgot(NOBODY)
        self.assertEqual(unknown.status_code, 200)
        self.assertEqual(unknown.json(), known.json())
        self.assertEqual(len(self.sender.messages), 1)
        self.assertNotIn(NOBODY, unknown.text)

    def test_email_is_normalized(self) -> None:
        self.create_user(ALICE)
        self.assertEqual(self.forgot(f"  {ALICE.upper()} ").status_code, 200)
        self.assertEqual(self.sender.messages[0].to, ALICE)

    def test_inactive_user_gets_no_email(self) -> None:
        user_id, _ = self.create_user(ALICE)
        self.service.repository.update_user(user_id, {"is_active": False})
        self.assertEqual(self.forgot(ALICE).status_code, 200)
        self.assertEqual(self.sender.messages, [])

    def test_invalid_payload_is_422(self) -> None:
        for body in ({"email": "not-an-email"}, {}, {"email": ALICE, "role": "admin"}):
            with self.subTest(body=body):
                self.assertEqual(self.client.post(FORGOT_URL, json=body).status_code, 422)

    def test_only_the_token_hash_is_stored(self) -> None:
        self.create_user(ALICE)
        token = self.requested_token()
        [record] = self.raw_table("password_reset_tokens")
        self.assertEqual(record["token_hash"], hash_reset_token(token))
        self.assertIsNone(record["used_at"])
        self.assertEqual(datetime.fromisoformat(record["expires_at"]), self.clock.now + timedelta(minutes=30))
        self.assertNotIn(token, self.auth_db_path.read_text(encoding="utf-8"))

    def test_a_new_request_invalidates_the_previous_link(self) -> None:
        self.create_user(ALICE)
        first = self.requested_token()
        second = self.requested_token()
        self.assertInvalidToken(self.reset(first, new_password()))
        self.assertEqual(self.reset(second, new_password()).status_code, 200)

    def test_delivery_failure_does_not_change_the_response_nor_leak_data(self) -> None:
        self.create_user(ALICE)
        self.app.state.email_sender = FakeEmailSender(error=EmailDeliveryError("email provider rejected the message"))
        with capture_logs() as logs:
            response = self.forgot(ALICE)
        self.assertEqual(response.status_code, 200)
        self.assertIn("EmailDeliveryError", logs.text())
        self.assertNotIn(ALICE, logs.text())
        self.assertNotIn(RESET_PAGE, logs.text())  # ni el enlace con el token

    def test_without_email_configuration_nothing_is_sent(self) -> None:
        self.create_user(ALICE)
        self.app.state.email_sender = DisabledEmailSender()
        with capture_logs() as logs:
            self.assertEqual(self.forgot(ALICE).status_code, 200)
        self.assertIn("EmailNotConfiguredError", logs.text())


class ResetPasswordTests(PasswordTestCase):
    def test_valid_token_changes_the_password(self) -> None:
        _, old_password = self.create_user(ALICE)
        password = new_password()
        response = self.reset(self.requested_token(), password)
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(self.login(ALICE, password).status_code, 200)
        self.assertEqual(self.login(ALICE, old_password).status_code, 401)
        [record] = self.raw_table("password_reset_tokens")
        self.assertIsNotNone(record["used_at"])

    def test_token_cannot_be_used_twice(self) -> None:
        self.create_user(ALICE)
        token = self.requested_token()
        first_password = new_password()
        self.assertEqual(self.reset(token, first_password).status_code, 200)
        self.assertInvalidToken(self.reset(token, new_password()))
        self.assertEqual(self.login(ALICE, first_password).status_code, 200)

    def test_token_expires_after_the_configured_window(self) -> None:
        self.create_user(ALICE)
        token = self.requested_token()
        self.clock.advance(minutes=30)
        self.assertInvalidToken(self.reset(token, new_password()))

    def test_token_is_valid_just_before_expiring(self) -> None:
        self.create_user(ALICE)
        token = self.requested_token()
        self.clock.advance(minutes=29, seconds=59)
        self.assertEqual(self.reset(token, new_password()).status_code, 200)

    def test_unknown_token_is_400(self) -> None:
        self.create_user(ALICE)
        self.requested_token()
        self.assertInvalidToken(self.reset("not-a-real-token", new_password()))

    def test_new_password_rules_apply(self) -> None:
        self.create_user(ALICE)
        token = self.requested_token()
        for password in ("short", "x" * 73):
            with self.subTest(length=len(password)):
                self.assertEqual(self.reset(token, password).status_code, 422)
        self.assertEqual(self.reset(token, new_password()).status_code, 200)  # el 422 no gastó el token

    def test_error_never_echoes_the_token(self) -> None:
        response = self.reset("secret-token-value", new_password())
        self.assertNotIn("secret-token-value", response.text)


class ChangePasswordTests(PasswordTestCase):
    def change(self, token: str | None, current: str, new: str) -> Any:
        headers = bearer(token) if token else {}
        return self.client.post(CHANGE_URL, json={"current_password": current, "new_password": new}, headers=headers)

    def test_requires_a_session(self) -> None:
        self.assertUnauthorized(self.change(None, new_password(), new_password()))

    def test_wrong_current_password_is_400(self) -> None:
        _, password = self.create_user(ALICE)
        token = self.token_for(ALICE, password)
        response = self.change(token, "wrong-password", new_password())
        self.assertEqual(response.status_code, 400, response.text)
        self.assertEqual(response.json()["code"], "incorrect_password")
        self.assertEqual(self.login(ALICE, password).status_code, 200)

    def test_changes_the_password(self) -> None:
        _, password = self.create_user(ALICE)
        token = self.token_for(ALICE, password)
        new = new_password()
        response = self.change(token, password, new)
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(self.login(ALICE, new).status_code, 200)
        self.assertEqual(self.login(ALICE, password).status_code, 401)

    def test_change_invalidates_pending_reset_links(self) -> None:
        _, password = self.create_user(ALICE)
        reset_token = self.requested_token()
        self.assertEqual(self.change(self.token_for(ALICE, password), password, new_password()).status_code, 200)
        self.assertInvalidToken(self.reset(reset_token, new_password()))

    def test_new_password_rules_apply(self) -> None:
        _, password = self.create_user(ALICE)
        self.assertEqual(self.change(self.token_for(ALICE, password), password, "short").status_code, 422)


class AuditTests(PasswordTestCase):
    def test_password_events_are_recorded_without_personal_data_or_secrets(self) -> None:
        user_id, password = self.create_user(ALICE)
        self.forgot(NOBODY)
        token = self.requested_token()
        self.reset("not-a-real-token", new_password())
        reset_password = new_password()
        self.reset(token, reset_password)
        session = self.token_for(ALICE, reset_password)
        self.client.post(CHANGE_URL, json={"current_password": "wrong-password", "new_password": new_password()}, headers=bearer(session))
        self.client.post(CHANGE_URL, json={"current_password": reset_password, "new_password": new_password()}, headers=bearer(session))

        events = self.raw_table("password_audit")
        self.assertEqual(
            [(event["event"], event["user_id"], event["reason"]) for event in events],
            [
                ("reset_requested", None, "unknown_email"),
                ("reset_requested", user_id, None),
                ("reset_rejected", None, "unknown"),
                ("reset_completed", user_id, None),
                ("password_change_rejected", user_id, None),
                ("password_changed", user_id, None),
            ],
        )
        self.assertTrue(all(event["ip"] == "testclient" and event["created_at"] for event in events))
        audit_text = json.dumps(events)
        for secret in (ALICE, NOBODY, token, password, reset_password):
            self.assertNotIn(secret, audit_text)

    def test_reused_and_expired_tokens_are_audited_with_their_reason(self) -> None:
        self.create_user(ALICE)
        used = self.requested_token()
        self.reset(used, new_password())
        self.reset(used, new_password())
        expired = self.requested_token()
        self.clock.advance(hours=1)
        self.reset(expired, new_password())
        reasons = [event["reason"] for event in self.raw_table("password_audit") if event["event"] == "reset_rejected"]
        self.assertEqual(reasons, ["used", "expired"])


class EmailSettingsTests(unittest.TestCase):
    BASE = {"JWT_SECRET_KEY": "k" * 40, "ACCESS_TOKEN_EXPIRE_MINUTES": "30"}
    EMAIL = {"RESEND_API_KEY": "re_test_key", "EMAIL_FROM": "Nexova <onboarding@resend.dev>", "PASSWORD_RESET_URL": RESET_PAGE}

    def test_email_settings_are_read_from_the_environment(self) -> None:
        settings = Settings.from_env({**self.BASE, **self.EMAIL, "PASSWORD_RESET_TOKEN_EXPIRE_MINUTES": "15"})
        self.assertTrue(settings.email_configured)
        self.assertEqual(settings.password_reset_token_minutes, 15)
        self.assertNotIn("re_test_key", repr(settings))
        self.assertIsInstance(build_email_sender(settings), ResendEmailSender)

    def test_email_is_optional(self) -> None:
        settings = Settings.from_env(self.BASE)
        self.assertFalse(settings.email_configured)
        self.assertEqual(settings.password_reset_token_minutes, 30)
        self.assertIsInstance(build_email_sender(settings), DisabledEmailSender)

    def test_partial_email_configuration_is_rejected(self) -> None:
        for missing in self.EMAIL:
            with self.subTest(missing=missing), self.assertRaises(ConfigError):
                Settings.from_env({**self.BASE, **{k: v for k, v in self.EMAIL.items() if k != missing}})

    def test_reset_window_must_be_between_15_and_60_minutes(self) -> None:
        for value in ("14", "61", "0", "abc"):
            with self.subTest(value=value), self.assertRaises(ConfigError):
                Settings.from_env({**self.BASE, "PASSWORD_RESET_TOKEN_EXPIRE_MINUTES": value})

    def test_reset_url_must_be_absolute(self) -> None:
        with self.assertRaises(ConfigError):
            Settings.from_env({**self.BASE, **self.EMAIL, "PASSWORD_RESET_URL": "/reset-password"})


class ResendSenderTests(unittest.TestCase):
    def setUp(self) -> None:
        self.sender = ResendEmailSender("re_test_key", "Nexova <onboarding@resend.dev>")
        self.message = password_reset_message(ALICE, reset_link(RESET_PAGE, "tok_123"), 30)

    def test_builds_the_resend_request(self) -> None:
        request = self.sender.build_request(self.message)
        self.assertEqual((request.full_url, request.get_method()), (RESEND_EMAILS_URL, "POST"))
        self.assertEqual(request.get_header("Authorization"), "Bearer re_test_key")
        self.assertEqual(request.get_header("Content-type"), "application/json")
        self.assertNotIn("Python-urllib", request.get_header("User-agent"))
        assert isinstance(request.data, bytes)
        body = json.loads(request.data)
        self.assertEqual(body["to"], [ALICE])
        self.assertEqual(body["from"], "Nexova <onboarding@resend.dev>")
        self.assertIn(f"{RESET_PAGE}?token=tok_123", body["text"].splitlines())

    def test_successful_send(self) -> None:
        response = mock.MagicMock(status=200)
        response.__enter__.return_value = response
        with mock.patch("urllib.request.urlopen", return_value=response) as urlopen:
            self.sender.send(self.message)
        urlopen.assert_called_once()

    def test_provider_errors_become_email_delivery_error(self) -> None:
        errors = [
            urllib.error.HTTPError(RESEND_EMAILS_URL, 403, "Forbidden", {}, io.BytesIO(ALICE.encode())),  # type: ignore[arg-type]
            urllib.error.URLError("offline"),
            TimeoutError(),
        ]
        for error in errors:
            with self.subTest(error=type(error).__name__), mock.patch("urllib.request.urlopen", side_effect=error):
                with self.assertRaises(EmailDeliveryError) as raised:
                    self.sender.send(self.message)
                self.assertIsNone(raised.exception.__cause__)
                self.assertNotIn(ALICE, str(raised.exception))

    def test_secrets_are_not_in_reprs(self) -> None:
        self.assertNotIn("re_test_key", repr(self.sender))
        self.assertNotIn("tok_123", repr(self.message))

    def test_reset_link_encodes_the_token(self) -> None:
        self.assertEqual(reset_link(RESET_PAGE, "a+b/c"), f"{RESET_PAGE}?token=a%2Bb%2Fc")
        self.assertEqual(reset_link(f"{RESET_PAGE}?app=1", "t"), f"{RESET_PAGE}?app=1&token=t")


if __name__ == "__main__":
    unittest.main()

"""AUTH-01: comando `create-admin` (primer administrador)."""

import contextlib
import io
import json
import tempfile
import unittest
from collections.abc import Iterator
from pathlib import Path
from typing import Any
from unittest import mock

from passlib.hash import bcrypt

from app.auth.create_admin import run
from app.core.config import Settings

from .auth_support import new_password

ADMIN = "admin@example.invalid"


def answers(*values: str) -> Any:
    """Sustituye a `getpass`: devuelve las respuestas en orden."""
    iterator: Iterator[str] = iter(values)
    return lambda prompt: next(iterator)


class CreateAdminTestCase(unittest.TestCase):
    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.db_path = Path(tmp.name) / "auth.json"
        # Sin JWT: el comando no firma tokens y no debe exigirlo.
        self.settings = Settings(auth_db_path=self.db_path)

    def run_command(self, argv: list[str], *passwords: str) -> tuple[int, str]:
        output = io.StringIO()
        with contextlib.redirect_stdout(output), contextlib.redirect_stderr(output):
            code = run(argv, self.settings, read_password=answers(*passwords))
        return code, output.getvalue()

    def data(self) -> dict[str, Any]:
        result: dict[str, Any] = json.loads(self.db_path.read_text(encoding="utf-8"))
        return result


class CreateAdminTests(CreateAdminTestCase):
    def test_creates_admin_with_profile_and_bcrypt_hash(self) -> None:
        password = new_password()
        code, output = self.run_command(["--email", ADMIN, "--name", "Admin"], password, password)
        self.assertEqual(code, 0, output)
        [user] = self.data()["users"].values()
        [profile] = self.data()["profiles"].values()
        self.assertEqual((user["email"], user["role"], user["is_active"]), (ADMIN, "admin", True))
        self.assertTrue(bcrypt.verify(password, user["hashed_password"]))
        self.assertEqual((profile["user_id"], profile["name"]), (user["id"], "Admin"))
        self.assertNotIn(password, self.db_path.read_text(encoding="utf-8"))
        self.assertNotIn(password, output)
        self.assertIn(ADMIN, output)

    def test_existing_email_is_reported_and_nothing_changes(self) -> None:
        password = new_password()
        self.run_command(["--email", ADMIN], password, password)
        before = self.db_path.read_text(encoding="utf-8")
        code, output = self.run_command(["--email", ADMIN.upper()], password, password)
        self.assertEqual(code, 1)
        self.assertIn("ya existe", output)
        self.assertEqual(self.db_path.read_text(encoding="utf-8"), before)

    def test_mismatched_passwords_create_nothing(self) -> None:
        code, output = self.run_command(["--email", ADMIN], new_password(), new_password())
        self.assertEqual(code, 1)
        self.assertIn("no coinciden", output)
        self.assertFalse(self.db_path.exists())

    def test_invalid_input_is_rejected_without_echoing_it(self) -> None:
        for argv, password in ((["--email", "not-an-email"], new_password()), (["--email", ADMIN], "short-7")):
            with self.subTest(argv=argv):
                code, output = self.run_command(argv, password, password)
                self.assertEqual(code, 1)
                self.assertNotIn(password, output)
        self.assertFalse(self.db_path.exists())


class CreateAdminErrorTests(CreateAdminTestCase):
    """S3 de la auditoría: código 1, sin traceback, sin crear nada y sin mostrar la contraseña."""

    def assertNothingCreated(self, code: int, output: str, password: str | None = None) -> None:
        self.assertEqual(code, 1, output)
        self.assertNotIn("Traceback", output)
        self.assertNotIn("Administrador creado", output)
        if password is not None:
            self.assertNotIn(password, output)

    def test_eof_in_email_input_cancels(self) -> None:
        password = new_password()
        with mock.patch("builtins.input", side_effect=EOFError):
            code, output = self.run_command([], password, password)
        self.assertNothingCreated(code, output, password)
        self.assertIn("Operación cancelada. No se ha creado ningún usuario.", output)
        self.assertFalse(self.db_path.exists())

    def test_ctrl_c_in_getpass_cancels(self) -> None:
        password = new_password()

        def interrupted_confirmation(prompt: str) -> str:
            if prompt.startswith("Repite"):
                raise KeyboardInterrupt
            return password

        output = io.StringIO()
        try:
            with contextlib.redirect_stdout(output), contextlib.redirect_stderr(output):
                code = run(["--email", ADMIN], self.settings, read_password=interrupted_confirmation)
        except KeyboardInterrupt:
            # Sin esto, una regresión abortaría toda la suite en vez de fallar este test.
            self.fail("KeyboardInterrupt escaped from create-admin")
        self.assertNothingCreated(code, output.getvalue(), password)
        self.assertIn("Operación cancelada", output.getvalue())
        self.assertFalse(self.db_path.exists())

    def test_corrupt_database(self) -> None:
        corrupt = '{"users": {"1": {"email": "leak@example.invalid"'
        self.db_path.write_text(corrupt, encoding="utf-8")
        password = new_password()
        code, output = self.run_command(["--email", ADMIN], password, password)
        self.assertNothingCreated(code, output, password)
        self.assertIn("Error: no se pudo abrir o escribir la base de usuarios (auth.json)", output)
        self.assertIn("storage auth is unavailable: JSONDecodeError", output)
        for secret in (str(self.db_path.parent), "leak@example.invalid"):
            self.assertNotIn(secret, output)
        self.assertEqual(self.db_path.read_text(encoding="utf-8"), corrupt)

    def test_configuration_error(self) -> None:
        output = io.StringIO()
        with mock.patch.dict("os.environ", {"MAX_UPLOAD_BYTES": "not-a-number"}):
            with contextlib.redirect_stdout(output), contextlib.redirect_stderr(output):
                code = run(["--email", ADMIN], None, read_password=answers())
        self.assertNothingCreated(code, output.getvalue())
        self.assertIn("Error de configuración: MAX_UPLOAD_BYTES must be a positive integer", output.getvalue())


if __name__ == "__main__":
    unittest.main()

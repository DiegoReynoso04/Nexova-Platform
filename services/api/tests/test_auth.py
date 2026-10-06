"""AUTH-01: registro, contraseñas, login, JWT, /users, /profiles y /auth/me.

Los números entre corchetes remiten a la lista de tests pedida en el ticket.
"""

import unittest
from datetime import UTC, datetime, timedelta

from jose import jwt
from passlib.hash import bcrypt

from app.auth.models import UserRole
from app.auth.security import JWT_ALGORITHM, create_access_token

from .auth_support import AUTH_ME_URL, PROFILE_ME_URL, USERS_URL, AuthTestCase, bearer, new_password

ALICE = "alice@example.invalid"
BOB = "bob@example.invalid"
ADMIN = "admin@example.invalid"


class RegistrationTests(AuthTestCase):
    def test_register_creates_user(self) -> None:  # [1]
        response = self.register(ALICE, new_password())
        self.assertEqual(response.status_code, 201, response.text)
        body = response.json()
        self.assertEqual(set(body), {"id", "email", "role", "is_active", "created_at"})
        self.assertEqual(body["email"], ALICE)
        self.assertTrue(body["is_active"])
        self.assertNoCredentials(response)

    def test_password_is_stored_as_bcrypt_hash(self) -> None:  # [2]
        password = new_password()
        self.register(ALICE, password)
        [user] = self.raw_users()
        self.assertTrue(user["hashed_password"].startswith("$2b$"))
        self.assertTrue(bcrypt.verify(password, user["hashed_password"]))
        self.assertEqual(
            set(user), {"id", "email", "hashed_password", "is_active", "role", "created_at"}
        )  # sin nombre ni contacto en User

    def test_plain_password_never_reaches_the_database(self) -> None:  # [3]
        password = new_password()
        self.register(ALICE, password, name="Alice")
        self.assertNotIn(password, self.auth_db_path.read_text(encoding="utf-8"))
        self.assertNotIn("password", {key for user in self.raw_users() for key in user} - {"hashed_password"})

    def test_profile_is_created_with_the_user(self) -> None:  # [4]
        response = self.register(ALICE, new_password(), name="Alice", phone="+34 600 000 000", address="Valencia")
        [profile] = self.raw_profiles()
        self.assertEqual(profile["user_id"], response.json()["id"])
        self.assertEqual(
            (profile["name"], profile["phone"], profile["address"]), ("Alice", "+34 600 000 000", "Valencia")
        )
        self.assertNotEqual(profile["id"], profile["user_id"])

    def test_profile_is_created_even_without_profile_fields(self) -> None:  # [4]
        user_id = self.register(ALICE, new_password()).json()["id"]
        [profile] = self.raw_profiles()
        self.assertEqual(profile["user_id"], user_id)
        self.assertEqual((profile["name"], profile["phone"], profile["address"]), (None, None, None))

    def test_default_role_is_user(self) -> None:  # [5]
        self.assertEqual(self.register(ALICE, new_password()).json()["role"], "user")
        self.assertEqual(self.raw_users()[0]["role"], "user")

    def test_public_registration_does_not_accept_role(self) -> None:  # [6]
        # El registro público no admite `role` con ningún valor (válido o no):
        # el backend fija siempre `user`. Un rol inválido en PUT → test_admin_changes_role.
        for role in ("admin", "manager", "user", "superuser", "", 1):
            with self.subTest(role=role):
                response = self.register(f"r{role}@example.invalid", new_password(), role=role)
                self.assertEqual(response.status_code, 422, response.text)
        self.assertFalse(self.auth_db_path.exists() and self.raw_users())

    def test_duplicate_email_is_409(self) -> None:  # [7]
        self.register(ALICE, new_password())
        response = self.register(ALICE.upper(), new_password())  # el email se normaliza a minúsculas
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["code"], "email_already_registered")
        self.assertNotIn(ALICE, response.text)
        self.assertEqual(len(self.raw_users()), 1)

    def test_invalid_email_is_422(self) -> None:
        for email in ("", "alice", "alice@", "@example.invalid", "a@b", "a b@example.invalid", "a@@example.invalid"):
            with self.subTest(email=email):
                self.assertEqual(self.register(email, new_password()).status_code, 422)

    def test_password_limits_are_validated_before_hashing(self) -> None:
        too_long = "ñ" * 37  # 37 caracteres, 74 bytes en UTF-8: supera el límite de bcrypt
        for password in ("short", "x" * 73, too_long):
            with self.subTest(length=len(password)):
                response = self.register(ALICE, password)
                self.assertEqual(response.status_code, 422)
                self.assertNotIn(password, response.text)
        self.assertEqual(self.register(ALICE, "x" * 72).status_code, 201)

    def test_system_fields_cannot_be_sent(self) -> None:
        for field in ("hashed_password", "id", "is_active", "created_at", "user_id"):
            with self.subTest(field=field):
                response = self.register(ALICE, new_password(), **{field: "x"})
                self.assertEqual(response.status_code, 422)


class LoginAndTokenTests(AuthTestCase):
    def test_login_returns_a_bearer_token(self) -> None:  # [8]
        user_id, password = self.create_user(ALICE)
        response = self.login(ALICE, password)
        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        self.assertEqual(body["token_type"], "bearer")
        self.assertEqual(body["expires_in"], self.settings.access_token_expire_minutes * 60)  # type: ignore[operator]
        self.assertEqual(self.client.get(AUTH_ME_URL, headers=bearer(body["access_token"])).json()["id"], user_id)

    def test_login_email_is_case_insensitive(self) -> None:
        _, password = self.create_user(ALICE)
        self.assertEqual(self.login(ALICE.upper(), password).status_code, 200)

    def test_wrong_credentials_are_401_with_the_same_message(self) -> None:  # [9]
        _, password = self.create_user(ALICE)
        responses = [
            self.login(ALICE, password + "x"),
            self.login(BOB, password),
            self.login("not-an-email", password),
            self.login(ALICE, "x" * 100),
        ]
        for response in responses:
            with self.subTest(body=response.text):
                self.assertEqual(response.status_code, 401)
                self.assertEqual(response.json(), {"detail": "incorrect email or password", "code": "invalid_credentials"})
                self.assertEqual(response.headers.get("www-authenticate"), "Bearer")
                self.assertNotIn("access_token", response.text)

    def test_login_requires_the_oauth2_form(self) -> None:
        _, password = self.create_user(ALICE)
        response = self.client.post("/auth/login", json={"username": ALICE, "password": password})
        self.assertEqual(response.status_code, 422)
        self.assertNotIn(password, response.text)

    def test_token_contains_sub_and_exp(self) -> None:  # [10]
        user_id, password = self.create_user(ALICE)
        token = self.token_for(ALICE, password)
        claims = jwt.decode(token, self.settings.jwt_secret_key, algorithms=[JWT_ALGORITHM])
        self.assertEqual(claims["sub"], user_id)
        self.assertEqual(claims["exp"] - claims["iat"], self.settings.access_token_expire_minutes * 60)  # type: ignore[operator]
        self.assertEqual(jwt.get_unverified_header(token)["alg"], "HS256")
        self.assertNotIn(password, token)

    def test_expired_token_is_401(self) -> None:  # [11]
        user_id, _ = self.create_user(ALICE)
        issued = datetime.now(UTC) - timedelta(minutes=self.settings.access_token_expire_minutes + 1)  # type: ignore[operator]
        token = create_access_token(self.settings, user_id, now=issued)
        self.assertUnauthorized(self.client.get(AUTH_ME_URL, headers=bearer(token)))

    def test_malformed_or_forged_tokens_are_401(self) -> None:  # [12]
        user_id, password = self.create_user(ALICE)
        valid = self.token_for(ALICE, password)
        now = datetime.now(UTC)
        forged = {
            "garbage": "not-a-jwt",
            "truncated": valid[:-5],
            "tampered payload": valid.split(".")[0] + ".e30." + valid.split(".")[2],
            "other secret": jwt.encode({"sub": user_id, "exp": now + timedelta(minutes=5)}, "x" * 48, algorithm="HS256"),
            "no exp": jwt.encode({"sub": user_id}, self.settings.jwt_secret_key, algorithm="HS256"),
            "no sub": jwt.encode({"exp": now + timedelta(minutes=5)}, self.settings.jwt_secret_key, algorithm="HS256"),
            "unknown user": create_access_token(self.settings, "00000000-0000-4000-8000-000000000000"),
        }
        for name, token in forged.items():
            with self.subTest(token=name):
                self.assertUnauthorized(self.client.get(AUTH_ME_URL, headers=bearer(token)))
        for header in (f"Token {valid}", valid, "Bearer"):
            with self.subTest(header=header[:12]):
                self.assertUnauthorized(self.client.get(AUTH_ME_URL, headers={"Authorization": header}))

    def test_alg_none_token_is_401(self) -> None:
        user_id, _ = self.create_user(ALICE)
        payload = create_access_token(self.settings, user_id).split(".")[1]  # claims válidos
        header = "eyJhbGciOiJub25lIiwidHlwIjoiSldUIn0"  # {"alg":"none","typ":"JWT"}
        token = f"{header}.{payload}."
        self.assertUnauthorized(self.client.get(AUTH_ME_URL, headers=bearer(token)))


class UsersEndpointTests(AuthTestCase):
    def test_list_users_without_token_is_401(self) -> None:  # [13]
        self.assertUnauthorized(self.client.get(USERS_URL))

    def test_list_users_as_user_is_403(self) -> None:  # [14]
        _, token = self.user_with_token(ALICE)
        self.assertForbidden(self.client.get(USERS_URL, headers=bearer(token)))

    def test_list_users_as_admin(self) -> None:  # [15]
        self.create_user(ALICE)
        _, token = self.user_with_token(ADMIN, UserRole.ADMIN)
        response = self.client.get(USERS_URL, headers=bearer(token))
        self.assertEqual(response.status_code, 200)
        self.assertEqual({user["email"] for user in response.json()}, {ALICE, ADMIN})
        self.assertNoCredentials(response)

    def test_user_reads_itself(self) -> None:  # [16]
        user_id, token = self.user_with_token(ALICE)
        response = self.client.get(f"{USERS_URL}/{user_id}", headers=bearer(token))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["email"], ALICE)
        self.assertNoCredentials(response)

    def test_user_cannot_access_another_user(self) -> None:  # [17]
        _, token = self.user_with_token(ALICE)
        bob_id, bob_password = self.create_user(BOB)
        url = f"{USERS_URL}/{bob_id}"
        self.assertForbidden(self.client.get(url, headers=bearer(token)))
        self.assertForbidden(self.client.put(url, json={"email": "stolen@example.invalid"}, headers=bearer(token)))
        self.assertForbidden(self.client.put(url, json={"password": new_password()}, headers=bearer(token)))
        self.assertForbidden(self.client.delete(url, headers=bearer(token)))
        # Bob sigue intacto y puede hacer login con su contraseña.
        self.assertEqual(self.login(BOB, bob_password).status_code, 200)
        # Un id inexistente también es 403 para un no-admin (no revela qué ids existen).
        missing = f"{USERS_URL}/00000000-0000-4000-8000-000000000000"
        self.assertForbidden(self.client.get(missing, headers=bearer(token)))

    def test_admin_accesses_other_users(self) -> None:
        bob_id, _ = self.create_user(BOB)
        _, token = self.user_with_token(ADMIN, UserRole.ADMIN)
        self.assertEqual(self.client.get(f"{USERS_URL}/{bob_id}", headers=bearer(token)).json()["email"], BOB)
        missing = f"{USERS_URL}/00000000-0000-4000-8000-000000000000"
        self.assertEqual(self.client.get(missing, headers=bearer(token)).json()["code"], "user_not_found")

    def test_invalid_user_id_is_422(self) -> None:
        _, token = self.user_with_token(ADMIN, UserRole.ADMIN)
        self.assertEqual(self.client.get(f"{USERS_URL}/1", headers=bearer(token)).status_code, 422)

    def test_user_updates_own_email(self) -> None:  # [18]
        user_id, password = self.create_user(ALICE)
        token = self.token_for(ALICE, password)
        response = self.client.put(f"{USERS_URL}/{user_id}", json={"email": "alice.new@example.invalid"}, headers=bearer(token))
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["email"], "alice.new@example.invalid")
        self.assertEqual(response.json()["role"], "user")
        self.assertNoCredentials(response)
        self.assertEqual(self.login("alice.new@example.invalid", password).status_code, 200)
        self.assertEqual(self.login(ALICE, password).status_code, 401)

    def test_user_cannot_change_own_password_with_put(self) -> None:  # AUTH-03, auditoría H-1
        # Sin la contraseña actual no se puede cambiar: solo POST /auth/change-password.
        user_id, password = self.create_user(ALICE)
        token = self.token_for(ALICE, password)
        stored_hash = self.raw_users()[0]["hashed_password"]
        for body in ({"password": new_password()}, {"email": "alice.new@example.invalid", "password": new_password()}):
            with self.subTest(fields=sorted(body)):
                response = self.client.put(f"{USERS_URL}/{user_id}", json=body, headers=bearer(token))
                self.assertForbidden(response)
                self.assertNotIn(body["password"], response.text)
        # No se aplicó nada, tampoco el email enviado junto a la contraseña.
        self.assertEqual(self.raw_users()[0]["hashed_password"], stored_hash)
        self.assertEqual(self.raw_users()[0]["email"], ALICE)
        self.assertEqual(self.login(ALICE, password).status_code, 200)

    def test_manager_cannot_change_own_password_with_put(self) -> None:  # AUTH-03, auditoría H-1
        user_id, password = self.create_user("manager@example.invalid", UserRole.MANAGER)
        token = self.token_for("manager@example.invalid", password)
        response = self.client.put(f"{USERS_URL}/{user_id}", json={"password": new_password()}, headers=bearer(token))
        self.assertForbidden(response)
        self.assertEqual(self.login("manager@example.invalid", password).status_code, 200)

    def test_user_cannot_change_another_users_password(self) -> None:  # AUTH-03, auditoría H-1
        bob_id, bob_password = self.create_user(BOB)
        _, token = self.user_with_token(ALICE)
        response = self.client.put(f"{USERS_URL}/{bob_id}", json={"password": new_password()}, headers=bearer(token))
        self.assertForbidden(response)
        self.assertEqual(self.login(BOB, bob_password).status_code, 200)

    def test_admin_can_still_set_another_users_password(self) -> None:  # capacidad de admin de AUTH-01
        bob_id, bob_password = self.create_user(BOB)
        _, token = self.user_with_token(ADMIN, UserRole.ADMIN)
        new = new_password()
        response = self.client.put(f"{USERS_URL}/{bob_id}", json={"password": new}, headers=bearer(token))
        self.assertEqual(response.status_code, 200, response.text)
        self.assertNoCredentials(response)
        self.assertNotIn(new, self.auth_db_path.read_text(encoding="utf-8"))
        self.assertEqual(self.login(BOB, new).status_code, 200)
        self.assertEqual(self.login(BOB, bob_password).status_code, 401)

    def test_change_password_endpoint_remains_the_way_for_users(self) -> None:  # AUTH-03, auditoría H-1
        user_id, password = self.create_user(ALICE)
        token = self.token_for(ALICE, password)
        self.assertForbidden(self.client.put(f"{USERS_URL}/{user_id}", json={"password": new_password()}, headers=bearer(token)))
        wrong = self.client.post(
            "/auth/change-password", json={"current_password": "wrong-password", "new_password": new_password()}, headers=bearer(token)
        )
        self.assertEqual(wrong.status_code, 400, wrong.text)
        self.assertEqual(wrong.json()["code"], "incorrect_password")
        new = new_password()
        changed = self.client.post(
            "/auth/change-password", json={"current_password": password, "new_password": new}, headers=bearer(token)
        )
        self.assertEqual(changed.status_code, 200, changed.text)
        self.assertEqual(self.login(ALICE, new).status_code, 200)
        self.assertEqual(self.login(ALICE, password).status_code, 401)

    def test_update_to_an_existing_email_is_409(self) -> None:
        user_id, token = self.user_with_token(ALICE)
        self.create_user(BOB)
        response = self.client.put(f"{USERS_URL}/{user_id}", json={"email": BOB}, headers=bearer(token))
        self.assertEqual(response.status_code, 409)

    def test_user_cannot_change_own_role(self) -> None:  # [19]
        user_id, token = self.user_with_token(ALICE)
        for role in ("admin", "manager", "user"):
            with self.subTest(role=role):
                response = self.client.put(f"{USERS_URL}/{user_id}", json={"role": role}, headers=bearer(token))
                self.assertForbidden(response)
        # Tampoco colándolo junto a un cambio permitido: no se aplica nada.
        response = self.client.put(
            f"{USERS_URL}/{user_id}", json={"email": "x@example.invalid", "role": "admin"}, headers=bearer(token)
        )
        self.assertForbidden(response)
        self.assertEqual(self.raw_users()[0]["role"], "user")
        self.assertEqual(self.raw_users()[0]["email"], ALICE)

    def test_admin_changes_role(self) -> None:  # [20]
        bob_id, bob_password = self.create_user(BOB)
        _, token = self.user_with_token(ADMIN, UserRole.ADMIN)
        response = self.client.put(f"{USERS_URL}/{bob_id}", json={"role": "manager"}, headers=bearer(token))
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["role"], "manager")
        bob_token = self.token_for(BOB, bob_password)
        self.assertEqual(self.client.get(AUTH_ME_URL, headers=bearer(bob_token)).json()["role"], "manager")
        invalid = self.client.put(f"{USERS_URL}/{bob_id}", json={"role": "root"}, headers=bearer(token))
        self.assertEqual(invalid.status_code, 422)  # [6] también en PUT

    def test_user_deletes_own_account_and_profile(self) -> None:  # [21]
        user_id, token = self.user_with_token(ALICE, name="Alice")
        bob_id, _ = self.create_user(BOB, name="Bob")
        response = self.client.delete(f"{USERS_URL}/{user_id}", headers=bearer(token))
        self.assertEqual(response.status_code, 204)
        self.assertEqual([user["id"] for user in self.raw_users()], [bob_id])
        self.assertEqual([profile["user_id"] for profile in self.raw_profiles()], [bob_id])
        # El token del usuario borrado deja de valer.
        self.assertUnauthorized(self.client.get(AUTH_ME_URL, headers=bearer(token)))

    def test_admin_deletes_another_user_and_profile(self) -> None:
        bob_id, _ = self.create_user(BOB)
        _, token = self.user_with_token(ADMIN, UserRole.ADMIN)
        self.assertEqual(self.client.delete(f"{USERS_URL}/{bob_id}", headers=bearer(token)).status_code, 204)
        self.assertNotIn(bob_id, {profile["user_id"] for profile in self.raw_profiles()})
        self.assertEqual(self.client.delete(f"{USERS_URL}/{bob_id}", headers=bearer(token)).status_code, 404)

    def test_every_profile_belongs_to_an_existing_user(self) -> None:
        for email in (ALICE, BOB):
            self.create_user(email)
        user_ids = {user["id"] for user in self.raw_users()}
        profiles = self.raw_profiles()
        self.assertEqual(len(profiles), len(user_ids))
        self.assertEqual({profile["user_id"] for profile in profiles}, user_ids)


class ProfileEndpointTests(AuthTestCase):
    def test_profile_me_without_token_is_401(self) -> None:  # [22]
        self.assertUnauthorized(self.client.get(PROFILE_ME_URL))
        self.assertUnauthorized(self.client.put(PROFILE_ME_URL, json={"name": "x"}))

    def test_profile_me_with_token(self) -> None:  # [23]
        user_id, token = self.user_with_token(ALICE, name="Alice", phone="600")
        response = self.client.get(PROFILE_ME_URL, headers=bearer(token))
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual((body["user_id"], body["name"], body["phone"], body["address"]), (user_id, "Alice", "600", None))

    def test_update_own_profile(self) -> None:
        _, token = self.user_with_token(ALICE, name="Alice", phone="600")
        response = self.client.put(PROFILE_ME_URL, json={"name": "Alice R.", "address": "Valencia"}, headers=bearer(token))
        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        self.assertEqual((body["name"], body["phone"], body["address"]), ("Alice R.", "600", "Valencia"))
        cleared = self.client.put(PROFILE_ME_URL, json={"phone": None}, headers=bearer(token)).json()
        self.assertIsNone(cleared["phone"])

    def test_profile_owner_comes_from_the_token_not_the_body(self) -> None:
        _, alice_token = self.user_with_token(ALICE, name="Alice")
        bob_id, _ = self.create_user(BOB, name="Bob")
        response = self.client.put(
            PROFILE_ME_URL, json={"user_id": bob_id, "name": "Hacked"}, headers=bearer(alice_token)
        )
        self.assertEqual(response.status_code, 422)
        self.client.put(PROFILE_ME_URL, json={"name": "Alice 2"}, headers=bearer(alice_token))
        names = {profile["user_id"]: profile["name"] for profile in self.raw_profiles()}
        self.assertEqual(names[bob_id], "Bob")


class AuthMeTests(AuthTestCase):
    def test_auth_me_without_token_is_401(self) -> None:  # [24]
        self.assertUnauthorized(self.client.get(AUTH_ME_URL))

    def test_auth_me_returns_user_and_profile_without_credentials(self) -> None:  # [25]
        user_id, token = self.user_with_token(ALICE, name="Alice", phone="600", address="Valencia")
        response = self.client.get(AUTH_ME_URL, headers=bearer(token))
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual((body["id"], body["email"], body["role"]), (user_id, ALICE, "user"))
        self.assertEqual(
            (body["profile"]["name"], body["profile"]["phone"], body["profile"]["address"]),
            ("Alice", "600", "Valencia"),
        )
        self.assertEqual(body["profile"]["user_id"], user_id)
        self.assertNoCredentials(response)


if __name__ == "__main__":
    unittest.main()

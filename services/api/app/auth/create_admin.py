"""Comando `uv run create-admin`: crea un usuario con `role=admin` y su `Profile`.

Ejecución (desde `services/api`):

    uv run --env-file .env create-admin --email admin@example.com --name "Nombre"

Sin uv, con el venv del servicio: `python -m app.auth.create_admin ...`.

- La contraseña se pide de forma interactiva y oculta (`getpass`), dos veces;
  nunca como argumento de línea de comandos (quedaría en el historial de la
  shell) ni en el repositorio. No se imprime.
- Misma validación que `POST /users` (email, 8 caracteres mínimo, 72 bytes
  máximo por bcrypt) y mismo servicio: se guarda solo el hash bcrypt.
- Usa la misma base que la API (`AUTH_DB_PATH` o services/api/data/auth.json).
- Si el email ya existe, lo indica y termina con código 1 sin tocar nada.
- También termina con código 1, sin traceback ni crear nada, ante un error de
  configuración, una entrada cancelada (Ctrl+C o fin de entrada) o una base
  que no se puede abrir, escribir o está corrupta.
"""

import argparse
import getpass
import sys
from collections.abc import Callable, Sequence

from pydantic import ValidationError

from app.auth.models import UserCreate, UserRole
from app.auth.repository import AuthRepository
from app.auth.service import UserService
from app.core.config import ConfigError, Settings
from app.core.errors import EmailAlreadyRegisteredError, StorageUnavailableError


def run(
    argv: Sequence[str] | None = None,
    settings: Settings | None = None,
    read_password: Callable[[str], str] = getpass.getpass,
) -> int:
    parser = argparse.ArgumentParser(prog="create-admin", description="Crea el primer administrador de la API.")
    parser.add_argument("--email", help="Email del administrador (si no se indica, se pide)")
    parser.add_argument("--name", help="Nombre visible del administrador (opcional, va al Profile)")
    args = parser.parse_args(argv)
    if settings is None:
        try:
            settings = Settings.from_env()
        except ConfigError as error:
            # Los mensajes de ConfigError son fijos: nombran la variable, nunca su valor.
            print(f"Error de configuración: {error}", file=sys.stderr)
            return 1
    service = UserService(AuthRepository(settings.auth_db_path))

    try:
        email = args.email if args.email else input("Email del administrador: ")
        password = read_password("Contraseña: ")
        confirmation = read_password("Repite la contraseña: ")
    except (EOFError, KeyboardInterrupt):
        # Ctrl+C, Ctrl+D/Ctrl+Z o entrada cerrada: no se ha tocado la base.
        print("\nOperación cancelada. No se ha creado ningún usuario.", file=sys.stderr)
        return 1
    if confirmation != password:
        print("Error: las contraseñas no coinciden. No se ha creado ningún usuario.", file=sys.stderr)
        return 1
    try:
        payload = UserCreate(email=email, password=password, name=args.name)
    except ValidationError as error:
        # Solo los mensajes de validación: nunca el valor recibido.
        for detail in error.errors(include_input=False, include_url=False, include_context=False):
            print(f"Error: {detail['msg']}", file=sys.stderr)
        return 1

    try:
        if service.get_user_by_email(payload.email) is not None:
            print(f"Error: ya existe un usuario con el email {payload.email}. No se ha modificado nada.", file=sys.stderr)
            return 1
        user, _ = service.create_user(payload, role=UserRole.ADMIN)
    except EmailAlreadyRegisteredError:
        print(f"Error: ya existe un usuario con el email {payload.email}. No se ha modificado nada.", file=sys.stderr)
        return 1
    except StorageUnavailableError:
        # El repositorio ya registró el almacén y la clase del error; aquí solo
        # el nombre del archivo, nunca la ruta completa ni el mensaje original.
        print(
            f"Error: no se pudo abrir o escribir la base de usuarios ({settings.auth_db_path.name}). "
            "Revisa AUTH_DB_PATH, los permisos y que sea un archivo TinyDB válido.",
            file=sys.stderr,
        )
        return 1

    print(f"Base de datos: {settings.auth_db_path}")
    print(f"Administrador creado: {user.email} (id {user.id})")
    return 0


def main() -> None:
    """Punto de entrada de `uv run create-admin` (`[project.scripts]` en pyproject.toml)."""
    sys.exit(run())


if __name__ == "__main__":
    main()

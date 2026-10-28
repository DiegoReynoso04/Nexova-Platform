"""Cobertura de la serialización de toda la API (auditoría de serialización, D7).

Fija el entregable mínimo del brief: cada endpoint declara `response_model` en
su decorador y ninguno devuelve un modelo de almacenamiento (documento de
TinyDB) ni un modelo ORM de SQLModel. Las rutas sin cuerpo JSON (exportación
CSV y `DELETE` 204) lo declaran como `None` y documentan su respuesta en
`responses=`. Además, ninguna respuesta lleva credenciales ni, en los flujos
de auth no autenticados, el email. Ver docs/serialization-audit.md.
"""

import ast
import json
import types
import unittest
from typing import Any, Union, get_args, get_origin

from fastapi.routing import APIRoute, iter_route_contexts
from pydantic import BaseModel
from sqlmodel import SQLModel

from app.auth.models import Profile, UserInDB
from app.models import Supplier
from app.modules.incident_manager.models import Incident

from .support import APP_DIR, make_client

HTTP_METHODS = {"get", "post", "put", "patch", "delete"}
# Documentos de almacenamiento: nunca son la respuesta de una ruta.
STORAGE_MODELS = {UserInDB, Profile, Supplier, Incident}
# Únicas rutas sin cuerpo JSON: `response_model=None` y su respuesta en `responses=`.
NO_JSON_BODY = {
    ("GET", "/api/incidents/results/export"): 200,
    ("DELETE", "/users/{user_id}"): 204,
    ("DELETE", "/suppliers/{supplier_id}"): 204,
}
# Flujos de auth sin sesión: su respuesta no reenvía el email (brief).
UNAUTHENTICATED_AUTH_FLOWS = [
    ("/users", "post", "201"),
    ("/auth/login", "post", "200"),
    ("/auth/forgot-password", "post", "200"),
    ("/auth/reset-password", "post", "200"),
]
SENSITIVE_FIELDS = {"password", "hashed_password", "token_hash", "user_id"}


def route_decorators() -> list[tuple[str, int, ast.Call]]:
    """Cada `@router.<método>(...)` / `@app.<método>(...)` del código de la app."""
    found = []
    for path in sorted(APP_DIR.rglob("*.py")):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"), filename=str(path))):
            if isinstance(node, ast.FunctionDef):
                for decorator in node.decorator_list:
                    if (
                        isinstance(decorator, ast.Call)
                        and isinstance(decorator.func, ast.Attribute)
                        and decorator.func.attr in HTTP_METHODS
                        and isinstance(decorator.func.value, ast.Name)
                        and decorator.func.value.id in {"router", "app"}
                    ):
                        found.append((path.relative_to(APP_DIR).as_posix(), node.lineno, decorator))
    return found


def models_in(annotation: Any) -> list[type]:
    """Clases dentro de un `response_model` (`list[X]`, `X | Y`, `Annotated[...]`)."""
    if isinstance(annotation, type) and get_origin(annotation) is None:
        return [annotation]
    origin = get_origin(annotation)
    if origin in (list, Union, types.UnionType) or origin is not None:
        return [model for argument in get_args(annotation) for model in models_in(argument)]
    return []


class ResponseModelCoverageTests(unittest.TestCase):
    def setUp(self) -> None:
        self.client = make_client()
        self.addCleanup(self.client.auth_dir.cleanup)  # type: ignore[attr-defined]
        self.routes = [
            route
            for route in iter_route_contexts(list(self.client.app.routes))  # type: ignore[attr-defined]
            if isinstance(route.original_route, APIRoute)
        ]

    def test_every_route_decorator_declares_response_model(self) -> None:
        decorators = route_decorators()
        self.assertGreaterEqual(len(decorators), 32)
        for file, line, decorator in decorators:
            with self.subTest(route=f"{file}:{line}"):
                self.assertIn("response_model", {keyword.arg for keyword in decorator.keywords})

    def test_the_app_has_the_32_audited_endpoints(self) -> None:
        endpoints = {(method, route.path_format) for route in self.routes for method in route.methods}
        self.assertEqual(len(endpoints), 32)

    def test_json_routes_return_pydantic_schemas_never_storage_or_orm_models(self) -> None:
        for route in self.routes:
            for method in route.methods:
                with self.subTest(route=f"{method} {route.path_format}"):
                    if (method, route.path_format) in NO_JSON_BODY:
                        self.assertIsNone(route.response_model)
                        continue
                    models = models_in(route.response_model)
                    self.assertTrue(models, "response_model must name a schema")
                    for model in models:
                        self.assertTrue(issubclass(model, BaseModel), model)
                        self.assertNotIn(model, STORAGE_MODELS)
                        self.assertFalse(issubclass(model, SQLModel), model)

    def test_routes_without_json_body_document_their_response(self) -> None:
        operations = self.client.get("/openapi.json").json()["paths"]
        for (method, path), status in NO_JSON_BODY.items():
            with self.subTest(route=f"{method} {path}"):
                [route] = [r for r in self.routes if r.path_format == path and method in r.methods]
                self.assertIn(status, route.responses)
                documented = operations[path][method.lower()]["responses"][str(status)]
                self.assertTrue(documented["description"])
        export = operations["/api/incidents/results/export"]["get"]["responses"]["200"]
        self.assertIn("text/csv", export["content"])
        self.assertIn("X-Analysis-Id", export["headers"])


class ResponseContentTests(unittest.TestCase):
    def setUp(self) -> None:
        client = make_client()
        self.addCleanup(client.auth_dir.cleanup)  # type: ignore[attr-defined]
        self.client = client
        self.openapi = client.get("/openapi.json").json()

    def response_properties(self, path: str, method: str, status: str) -> set[str]:
        schema = self.openapi["paths"][path][method]["responses"][status]["content"]["application/json"]["schema"]
        name = schema["$ref"].rsplit("/", 1)[-1]
        return set(self.openapi["components"]["schemas"][name]["properties"])

    def test_no_response_schema_has_credentials_or_internal_keys(self) -> None:
        response_refs = {
            ref
            for operations in self.openapi["paths"].values()
            for operation in operations.values()
            for status, response in operation["responses"].items()
            if status.startswith("2")
            for ref in _refs(response)
        }
        components = self.openapi["components"]["schemas"]
        # Cierre transitivo: también los esquemas anidados (p. ej. el perfil dentro de /auth/me).
        pending = set(response_refs)
        while pending:
            nested = _refs(components[pending.pop()]) - response_refs
            response_refs |= nested
            pending |= nested
        self.assertIn("ProfileRead", response_refs)
        for name in response_refs:
            with self.subTest(schema=name):
                self.assertFalse(SENSITIVE_FIELDS & set(components[name].get("properties", {})))
        self.assertFalse({model.__name__ for model in STORAGE_MODELS} & set(components))

    def test_unauthenticated_auth_flows_do_not_return_the_email(self) -> None:
        for path, method, status in UNAUTHENTICATED_AUTH_FLOWS:
            with self.subTest(path=path):
                self.assertNotIn("email", self.response_properties(path, method, status))
        # `GET /auth/me` sí lo devuelve: es el del propio llamante (brief).
        self.assertIn("email", self.response_properties("/auth/me", "get", "200"))

    def test_health_is_typed_and_keeps_its_body(self) -> None:
        self.assertEqual(self.client.get("/health").json(), {"status": "ok"})
        self.assertEqual(self.response_properties("/health", "get", "200"), {"status"})


def _refs(node: Any) -> set[str]:
    """Nombres de los componentes referenciados (`$ref`) dentro de una respuesta de OpenAPI."""
    text = json.dumps(node)
    prefix = '"#/components/schemas/'
    return {part.split('"', 1)[0] for part in text.split(prefix)[1:]}


if __name__ == "__main__":
    unittest.main()

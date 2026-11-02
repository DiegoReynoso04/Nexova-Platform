"""Valida los esquemas de telemetría y su coherencia con el plan (D11 A del plan de telemetría).

Solo librería estándar: se ejecuta con cualquier Python ≥ 3.11, sin instalar
nada. No valida el metaesquema draft-07 completo (eso lo hizo una vez `ajv-cli`,
docs/telemetry/telemetry-plan.md §9.2), sino un subconjunto **cerrado** de
palabras clave: si `event-schemas.json` usa otra, el script falla en vez de
ignorarla en silencio.

Comprueba:

1. el envelope (las 8 claves, `additionalProperties: false`, `required`);
2. cada evento: `allOf` con el envelope, `event_type` en `const` con la
   taxonomía `entidad_accion`, `schemaVersion` en `const`, `additionalProperties:
   false` en `properties`, `required` ⊆ `properties`, y que el `oneOf` raíz los
   referencia todos;
3. el BRIEFING: los 5 obligatorios con su nombre exacto y, en los eventos de
   inventario, los 6 campos mínimos con sus valores literales;
4. contra `telemetry-plan.md`:
   - el catálogo (§4), las fichas (§6) y el JSON listan los mismos eventos, en
     el mismo orden, con los mismos metadatos (`$comment`);
   - la tabla de propiedades de cada ficha coincide con su esquema (nombre,
     tipo y obligatoriedad);
   - cada ficha tiene su frase;
   - **todo** bloque ```json del plan valida contra el esquema.

Uso (desde la raíz del monorepo):

    python scripts/validate_event_schemas.py
    python scripts/validate_event_schemas.py --dump-examples <carpeta>   # un .json por ejemplo, para ajv

Sale con 0 si todo cuadra y con 1 si no, con la lista de problemas.
"""

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
SCHEMA_PATH = ROOT / "docs" / "telemetry" / "event-schemas.json"
PLAN_PATH = ROOT / "docs" / "telemetry" / "telemetry-plan.md"

# Subconjunto de draft-07 que implementa `validate`.
SUPPORTED_KEYWORDS = {
    "$schema", "title", "description", "$comment", "definitions", "oneOf", "allOf", "$ref", "type",
    "properties", "required", "additionalProperties", "enum", "const", "pattern", "maxLength", "minimum",
    "maximum", "exclusiveMinimum", "items", "maxItems", "uniqueItems",
}
ENVELOPE_KEYS = ["eventId", "timestamp", "sessionId", "userId", "event_type", "schemaVersion", "requestId", "properties"]
EVENT_TYPE_PATTERN = re.compile(r"^[a-z]+(_[a-z]+)+$")
SCHEMA_VERSION = "1.0.0"

# BRIEFING de telemetría, §3: nombres exactos y campos mínimos.
MANDATORY_EVENTS = [
    "inbound_order_created", "outbound_order_created", "stock_threshold_triggered",
    "direct_stock_edit_rejected", "kit_cost_variance_detected",
]
INVENTORY_CATEGORY = "inventario"
MINIMUM_FIELDS = {
    "office": ["valencia", "miami"],
    "product_id": None,
    "product_category": ["training_kit", "certification", "onboarding_equipment"],
    "programme_id": None,
    "quantity": None,
    "currency": ["EUR", "USD"],
}

CATALOG_ROW = re.compile(
    r"^\| (\d+) \| `([a-z_]+)` \| ([^|]+) \| ([^|]+) \| (API|frontend) \| (stream|batch) \| ([^|]+) \|$"
)
SECTION_HEADING = re.compile(r"^#### `([a-z_]+)`$", re.MULTILINE)
META_LINE = re.compile(
    r"^- \*\*Clasificación:\*\* (.+?) · \*\*Categoría:\*\* (.+?) · \*\*Emisor:\*\* (API|frontend) · "
    r"\*\*Entrega:\*\* (stream|batch) · \*\*Prerrequisitos:\*\* (.+)$",
    re.MULTILINE,
)
PROPERTY_ROW = re.compile(r"^\| `([a-z0-9_]+)` \| `([^`]+)` \| (sí|no) \| .* \|$", re.MULTILINE)
JSON_BLOCK = re.compile(r"^```json\n(.*?)\n```$", re.MULTILINE | re.DOTALL)


# ---------------------------------------------------------------------------
# Validador del subconjunto de draft-07
# ---------------------------------------------------------------------------
def _is_type(value: Any, name: str) -> bool:
    if name == "null":
        return value is None
    if name == "boolean":
        return isinstance(value, bool)
    if name == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if name == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if name == "string":
        return isinstance(value, str)
    if name == "array":
        return isinstance(value, list)
    if name == "object":
        return isinstance(value, dict)
    raise ValueError(f"tipo desconocido: {name}")


def _json_equal(a: Any, b: Any) -> bool:
    """Igualdad de JSON: `true` no es `1`, y `1` sí es `1.0`."""
    if isinstance(a, bool) or isinstance(b, bool):
        return isinstance(a, bool) and isinstance(b, bool) and a == b
    return a == b and (a is None) == (b is None)


def _ecma_pattern(pattern: str) -> re.Pattern[str]:
    # En ECMA-262, `$` no acepta un salto de línea final; en Python, sí.
    if pattern.endswith("$") and not pattern.endswith("\\$"):
        pattern = pattern[:-1] + r"\Z"
    return re.compile(pattern)


def _resolve(root: dict[str, Any], ref: str) -> dict[str, Any]:
    if not ref.startswith("#/definitions/"):
        raise ValueError(f"$ref no soportado: {ref}")
    return root["definitions"][ref.removeprefix("#/definitions/")]


def validate(instance: Any, schema: dict[str, Any], root: dict[str, Any], path: str = "$") -> list[str]:
    errors: list[str] = []
    if "$ref" in schema:
        errors += validate(instance, _resolve(root, schema["$ref"]), root, path)
    for sub in schema.get("allOf", []):
        errors += validate(instance, sub, root, path)
    if "oneOf" in schema:
        matches = [sub for sub in schema["oneOf"] if not validate(instance, sub, root, path)]
        if len(matches) != 1:
            errors.append(f"{path}: cumple {len(matches)} esquemas de oneOf (debe cumplir 1)")
    if "type" in schema:
        names = schema["type"] if isinstance(schema["type"], list) else [schema["type"]]
        if not any(_is_type(instance, name) for name in names):
            errors.append(f"{path}: tipo {type(instance).__name__}, se esperaba {names}")
            return errors
    if "enum" in schema and not any(_json_equal(instance, option) for option in schema["enum"]):
        errors.append(f"{path}: {instance!r} no está en el enum")
    if "const" in schema and not _json_equal(instance, schema["const"]):
        errors.append(f"{path}: {instance!r} no es {schema['const']!r}")
    if isinstance(instance, str):
        if "pattern" in schema and not _ecma_pattern(schema["pattern"]).search(instance):
            errors.append(f"{path}: {instance!r} no cumple el patrón {schema['pattern']}")
        if "maxLength" in schema and len(instance) > schema["maxLength"]:
            errors.append(f"{path}: más de {schema['maxLength']} caracteres")
    if _is_type(instance, "number"):
        if "minimum" in schema and instance < schema["minimum"]:
            errors.append(f"{path}: menor que {schema['minimum']}")
        if "maximum" in schema and instance > schema["maximum"]:
            errors.append(f"{path}: mayor que {schema['maximum']}")
        if "exclusiveMinimum" in schema and instance <= schema["exclusiveMinimum"]:
            errors.append(f"{path}: no es mayor que {schema['exclusiveMinimum']}")
    if isinstance(instance, dict):
        properties = schema.get("properties", {})
        for key in schema.get("required", []):
            if key not in instance:
                errors.append(f"{path}: falta {key}")
        for key, value in instance.items():
            if key in properties:
                errors += validate(value, properties[key], root, f"{path}.{key}")
            elif schema.get("additionalProperties") is False:
                errors.append(f"{path}: clave no permitida {key!r}")
    if isinstance(instance, list):
        if "maxItems" in schema and len(instance) > schema["maxItems"]:
            errors.append(f"{path}: más de {schema['maxItems']} elementos")
        if schema.get("uniqueItems"):
            seen = [json.dumps(item, sort_keys=True) for item in instance]
            if len(seen) != len(set(seen)):
                errors.append(f"{path}: elementos repetidos")
        if "items" in schema:
            for index, item in enumerate(instance):
                errors += validate(item, schema["items"], root, f"{path}[{index}]")
    return errors


def unsupported_keywords(node: Any, path: str = "$") -> list[str]:
    """Palabras clave fuera de `SUPPORTED_KEYWORDS`, recorriendo solo posiciones de esquema."""
    if not isinstance(node, dict):
        return []
    problems = [f"{path}: palabra clave no soportada {key!r}" for key in node if key not in SUPPORTED_KEYWORDS]
    for key in ("definitions", "properties"):
        for name, sub in node.get(key, {}).items():
            problems += unsupported_keywords(sub, f"{path}.{key}.{name}")
    for key in ("allOf", "oneOf"):
        for index, sub in enumerate(node.get(key, [])):
            problems += unsupported_keywords(sub, f"{path}.{key}[{index}]")
    if isinstance(node.get("items"), dict):
        problems += unsupported_keywords(node["items"], f"{path}.items")
    return problems


# ---------------------------------------------------------------------------
# Comprobaciones
# ---------------------------------------------------------------------------
def parse_comment(comment: str) -> dict[str, str]:
    return dict(part.strip().split("=", 1) for part in comment.split(";"))


def type_token(schema: dict[str, Any]) -> str:
    """Tipo tal como lo escribe la tabla de propiedades del plan."""
    if "enum" in schema:
        nullable = any(option is None for option in schema["enum"])
        return "enum | null" if nullable else "enum"
    names = schema["type"] if isinstance(schema["type"], list) else [schema["type"]]
    base = next(name for name in names if name != "null")
    if base == "array":
        items = schema["items"]
        base = "array<enum>" if "enum" in items else f"array<{items['type']}>"
    return f"{base} | null" if "null" in names else base


def check_schema(schema: dict[str, Any]) -> tuple[list[str], list[str]]:
    """Problemas de estructura y la lista ordenada de eventos del JSON."""
    problems = unsupported_keywords(schema)
    definitions = schema.get("definitions", {})
    envelope = definitions.get("envelope")
    if envelope is None:
        return problems + ["falta definitions.envelope"], []
    if list(envelope.get("properties", {})) != ENVELOPE_KEYS or envelope.get("required") != ENVELOPE_KEYS:
        problems.append("envelope: las claves o `required` no son las 8 del plan, en su orden")
    if envelope.get("additionalProperties") is not False:
        problems.append("envelope: falta additionalProperties: false")

    events = [name for name in definitions if name != "envelope"]
    refs = [item.get("$ref") for item in schema.get("oneOf", [])]
    if refs != [f"#/definitions/{name}" for name in events]:
        problems.append("oneOf raíz: no referencia todos los eventos en el orden de definitions")
    for name in events:
        event = definitions[name]
        where = f"definitions.{name}"
        if not EVENT_TYPE_PATTERN.match(name):
            problems.append(f"{where}: el nombre no sigue entidad_accion")
        if event.get("allOf") != [{"$ref": "#/definitions/envelope"}]:
            problems.append(f"{where}: falta allOf con el envelope")
        overrides = event.get("properties", {})
        if overrides.get("event_type") != {"const": name}:
            problems.append(f"{where}: event_type no es const {name!r}")
        if overrides.get("schemaVersion") != {"const": SCHEMA_VERSION}:
            problems.append(f"{where}: schemaVersion no es const {SCHEMA_VERSION!r}")
        payload = overrides.get("properties", {})
        if payload.get("type") != "object" or payload.get("additionalProperties") is not False:
            problems.append(f"{where}: properties sin type object o sin additionalProperties: false")
        missing = set(payload.get("required", [])) - set(payload.get("properties", {}))
        if missing:
            problems.append(f"{where}: required sin definir: {sorted(missing)}")
        try:
            meta = parse_comment(event["$comment"])
        except (KeyError, ValueError):
            problems.append(f"{where}: $comment ausente o mal formado")
            continue
        if meta.get("categoría") == INVENTORY_CATEGORY:
            problems += check_minimum_fields(where, payload)
    missing_mandatory = [name for name in MANDATORY_EVENTS if name not in definitions]
    if missing_mandatory:
        problems.append(f"faltan obligatorios del BRIEFING: {missing_mandatory}")
    for name in events:
        is_mandatory = parse_comment(definitions[name].get("$comment", "clasificación=?")).get("clasificación") == "obligatorio"
        if is_mandatory != (name in MANDATORY_EVENTS):
            problems.append(f"definitions.{name}: la clasificación no coincide con el BRIEFING")
    return problems, events


def check_minimum_fields(where: str, payload: dict[str, Any]) -> list[str]:
    problems = []
    fields = payload.get("properties", {})
    for field, values in MINIMUM_FIELDS.items():
        if field not in fields or field not in payload.get("required", []):
            problems.append(f"{where}: falta el campo mínimo {field!r} del BRIEFING")
            continue
        if values is not None:
            declared = [option for option in fields[field].get("enum", []) if option is not None]
            if declared != values:
                problems.append(f"{where}.{field}: valores {declared}, el BRIEFING dice {values}")
    return problems


def check_plan(plan: str, schema: dict[str, Any], events: list[str]) -> tuple[list[str], list[Any]]:
    """Problemas de coherencia con el plan y los ejemplos JSON que contiene."""
    problems: list[str] = []
    definitions = schema["definitions"]

    catalog_match = re.search(r"<!-- CATALOG -->\n(.*?)\n<!-- /CATALOG -->", plan, re.DOTALL)
    if catalog_match is None:
        return ["plan: falta el catálogo entre <!-- CATALOG --> y <!-- /CATALOG -->"], []
    rows = [CATALOG_ROW.match(line) for line in catalog_match.group(1).splitlines()[2:]]
    if not all(rows):
        problems.append("catálogo: hay filas con otro formato")
    rows = [row for row in rows if row]
    if [row.group(2) for row in rows] != events:
        problems.append("catálogo (§4): la lista de eventos no es la del JSON (o no va en el mismo orden)")
    if [int(row.group(1)) for row in rows] != list(range(1, len(rows) + 1)):
        problems.append("catálogo (§4): la numeración no es correlativa")
    for row in rows:
        name = row.group(2)
        if name in definitions:
            problems += compare_meta(f"catálogo/{name}", row.groups()[2:], definitions[name])

    headings = list(SECTION_HEADING.finditer(plan))
    if [heading.group(1) for heading in headings] != events:
        problems.append("fichas (§6): la lista de eventos no es la del JSON (o no va en el mismo orden)")
    for index, heading in enumerate(headings):
        name = heading.group(1)
        end = headings[index + 1].start() if index + 1 < len(headings) else plan.find("\n## ", heading.end())
        section = plan[heading.end():end]
        if name not in definitions:
            continue
        problems += check_section(name, section, definitions[name])

    examples = []
    for block in JSON_BLOCK.finditer(plan):
        try:
            example = json.loads(block.group(1))
        except json.JSONDecodeError as error:
            problems.append(f"ejemplo en la línea {plan.count(chr(10), 0, block.start()) + 1}: JSON inválido ({error.msg})")
            continue
        errors = validate(example, schema, schema)
        line = plan.count("\n", 0, block.start()) + 1
        if errors:
            problems.append(f"ejemplo en la línea {line} ({example.get('event_type')}): " + "; ".join(errors[:3]))
        if isinstance(example, dict) and example.get("event_type") in definitions:
            errors = validate(example, definitions[example["event_type"]], schema)
            if errors:
                problems.append(f"ejemplo en la línea {line}: no valida contra su evento: " + "; ".join(errors[:3]))
        examples.append(example)
    return problems, examples


def compare_meta(where: str, values: tuple[str, ...], event: dict[str, Any]) -> list[str]:
    classification, category, emitter, delivery, prereqs = (value.strip() for value in values)
    meta = parse_comment(event["$comment"])
    plan_meta = {
        "clasificación": classification,
        "categoría": category,
        "emisor": emitter.lower(),
        "entrega": delivery,
        "prerrequisitos": ",".join(part.strip() for part in prereqs.split(",")),
    }
    return [f"{where}: {key} = {value!r} en el plan, {meta.get(key)!r} en el JSON"
            for key, value in plan_meta.items() if meta.get(key) != value]


def check_section(name: str, section: str, event: dict[str, Any]) -> list[str]:
    problems = []
    where = f"ficha/{name}"
    meta = META_LINE.search(section)
    if meta is None:
        problems.append(f"{where}: falta la línea de metadatos")
    else:
        problems += compare_meta(where, meta.groups(), event)
    phrase = f"- **Frase:** Capturamos `{name}` porque necesitamos saber "
    if phrase not in section or ", lo que nos permite decidir " not in section:
        problems.append(f"{where}: falta la frase «Capturamos… porque necesitamos saber…, lo que nos permite decidir…»")

    payload = event["properties"]["properties"]
    declared = payload.get("properties", {})
    required = set(payload.get("required", []))
    table = [(m.group(1), m.group(2).replace("\\|", "|"), m.group(3) == "sí") for m in PROPERTY_ROW.finditer(section)]
    if not table and declared:
        problems.append(f"{where}: falta la tabla de propiedades")
    if not declared and "Allowlist vacía" not in section:
        problems.append(f"{where}: allowlist vacía sin declarar")
    if [row[0] for row in table] != list(declared):
        problems.append(f"{where}: las propiedades de la tabla no son las del JSON (o no van en el mismo orden)")
    for prop, token, is_required in table:
        if prop not in declared:
            continue
        if type_token(declared[prop]) != token:
            problems.append(f"{where}.{prop}: tipo {token!r} en el plan, {type_token(declared[prop])!r} en el JSON")
        if is_required != (prop in required):
            problems.append(f"{where}.{prop}: la obligatoriedad no coincide")

    blocks = JSON_BLOCK.findall(section)
    if not blocks:
        problems.append(f"{where}: falta el ejemplo JSON")
    else:
        try:
            if json.loads(blocks[0]).get("event_type") != name:
                problems.append(f"{where}: el ejemplo es de otro evento")
        except (json.JSONDecodeError, AttributeError):
            pass  # Lo informa check_plan.
    return problems


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--dump-examples", type=Path, help="carpeta donde escribir cada ejemplo del plan como .json")
    args = parser.parse_args()

    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    # Con `core.autocrlf` el checkout de Windows trae CRLF.
    plan = PLAN_PATH.read_text(encoding="utf-8").replace("\r\n", "\n")
    problems, events = check_schema(schema)
    plan_problems, examples = check_plan(plan, schema, events)
    problems += plan_problems

    if args.dump_examples is not None:
        args.dump_examples.mkdir(parents=True, exist_ok=True)
        for index, example in enumerate(examples, 1):
            name = example.get("event_type", "example") if isinstance(example, dict) else "example"
            (args.dump_examples / f"{index:02d}-{name}.json").write_text(json.dumps(example, ensure_ascii=False, indent=2), encoding="utf-8")

    if problems:
        print(f"{len(problems)} problema(s):")
        for problem in problems:
            print(f"- {problem}")
        return 1
    mandatory = sum(name in MANDATORY_EVENTS for name in events)
    print(f"OK: {len(events)} eventos ({mandatory} obligatorios, {len(events) - mandatory} oportunidades), "
          f"{len(examples)} ejemplos validados contra event-schemas.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())

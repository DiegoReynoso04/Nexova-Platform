// Contrato de telemetría para los tests: docs/telemetry/event-schemas.json y un
// validador del subconjunto de draft-07 que usa (el mismo que implementa
// scripts/validate_event_schemas.py, en Python). Sin dependencias: así los
// eventos que construye el backoffice se validan contra el contrato real.

import { readFileSync } from 'node:fs';

export const CONTRACT = JSON.parse(readFileSync(new URL('../../../../docs/telemetry/event-schemas.json', import.meta.url), 'utf8'));
export const DEFINITIONS = CONTRACT.definitions;

const SUPPORTED = new Set([
  '$schema', 'title', 'description', '$comment', 'definitions', 'oneOf', 'allOf', '$ref', 'type', 'properties',
  'required', 'additionalProperties', 'enum', 'const', 'pattern', 'maxLength', 'minimum', 'maximum',
  'exclusiveMinimum', 'items', 'maxItems', 'uniqueItems',
]);

function isType(value, name) {
  switch (name) {
    case 'null': return value === null;
    case 'object': return typeof value === 'object' && value !== null && !Array.isArray(value);
    case 'array': return Array.isArray(value);
    case 'string': return typeof value === 'string';
    case 'boolean': return typeof value === 'boolean';
    case 'integer': return Number.isInteger(value);
    case 'number': return typeof value === 'number' && Number.isFinite(value);
    default: throw new Error(`tipo no soportado: ${name}`);
  }
}

const equal = (a, b) => JSON.stringify(a) === JSON.stringify(b);

/** Errores de `instance` contra `schema` (lista vacía = válido). */
export function validate(instance, schema, path = '$') {
  for (const key of Object.keys(schema)) if (!SUPPORTED.has(key)) throw new Error(`palabra clave no soportada: ${key}`);
  if (schema.$ref) {
    const name = schema.$ref.replace('#/definitions/', '');
    return validate(instance, DEFINITIONS[name], path);
  }
  const errors = [];
  if (schema.type !== undefined) {
    const types = Array.isArray(schema.type) ? schema.type : [schema.type];
    if (!types.some((type) => isType(instance, type))) return [`${path}: tipo ${JSON.stringify(schema.type)}`];
  }
  if ('const' in schema && !equal(instance, schema.const)) errors.push(`${path}: const ${JSON.stringify(schema.const)}`);
  if (schema.enum && !schema.enum.some((value) => equal(value, instance))) errors.push(`${path}: fuera del enum`);
  if (typeof instance === 'string') {
    if (schema.pattern && !new RegExp(schema.pattern, 'u').test(instance)) errors.push(`${path}: patrón ${schema.pattern}`);
    if (schema.maxLength !== undefined && [...instance].length > schema.maxLength) errors.push(`${path}: maxLength`);
  }
  if (typeof instance === 'number') {
    if (schema.minimum !== undefined && instance < schema.minimum) errors.push(`${path}: minimum`);
    if (schema.maximum !== undefined && instance > schema.maximum) errors.push(`${path}: maximum`);
    if (schema.exclusiveMinimum !== undefined && instance <= schema.exclusiveMinimum) errors.push(`${path}: exclusiveMinimum`);
  }
  if (Array.isArray(instance)) {
    if (schema.maxItems !== undefined && instance.length > schema.maxItems) errors.push(`${path}: maxItems`);
    if (schema.uniqueItems && new Set(instance.map((item) => JSON.stringify(item))).size !== instance.length) errors.push(`${path}: uniqueItems`);
    if (schema.items) instance.forEach((item, index) => errors.push(...validate(item, schema.items, `${path}[${index}]`)));
  }
  if (isType(instance, 'object')) {
    for (const key of schema.required ?? []) if (!(key in instance)) errors.push(`${path}: falta ${key}`);
    const properties = schema.properties ?? {};
    for (const [key, value] of Object.entries(instance)) {
      if (key in properties) errors.push(...validate(value, properties[key], `${path}.${key}`));
      else if (schema.additionalProperties === false) errors.push(`${path}: clave no permitida ${key}`);
    }
  }
  for (const sub of schema.allOf ?? []) errors.push(...validate(instance, sub, path));
  if (schema.oneOf) {
    const matches = schema.oneOf.filter((sub) => validate(instance, sub, path).length === 0).length;
    if (matches !== 1) errors.push(`${path}: oneOf (${matches} coincidencias)`);
  }
  return errors;
}

/** Errores de un evento contra la raíz del contrato y contra su propia definición. */
export function eventErrors(event) {
  const definition = DEFINITIONS[event?.event_type];
  if (definition === undefined) return [`event_type desconocido: ${event?.event_type}`];
  return [...validate(event, CONTRACT), ...validate(event, definition)];
}

/** Metadatos del `$comment` de cada evento (`emisor=frontend; …`). */
export function eventMeta(name) {
  return Object.fromEntries(DEFINITIONS[name].$comment.split('; ').map((pair) => pair.split('=')));
}

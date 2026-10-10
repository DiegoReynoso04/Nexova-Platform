// Reglas estáticas sobre el código de producción del tracker (auditoría de
// gestión de errores, T1 y T2): existen los límites de error de Next 16, y la
// UI nunca muestra el mensaje crudo de un error, su digest ni hace console.*.
// Se analiza el código sin comentarios (mismo criterio que el backoffice).

import assert from 'node:assert/strict';
import { readFileSync, readdirSync } from 'node:fs';
import { describe, test } from 'node:test';

const APP_ROOT = new URL('../', import.meta.url);
const UI_DIRS = ['app', 'components'];
const PRODUCTION_DIRS = [...UI_DIRS, 'hooks', 'lib', 'services', 'types'];

function filesIn(dirs) {
  return dirs
    .flatMap((dir) =>
      readdirSync(new URL(`${dir}/`, APP_ROOT), { recursive: true }).map((entry) => `${dir}/${String(entry).replaceAll('\\', '/')}`)
    )
    .filter((path) => /\.tsx?$/.test(path))
    .sort();
}

const UI_FILES = filesIn(UI_DIRS);
const PRODUCTION_FILES = filesIn(PRODUCTION_DIRS);

function codeWithoutComments(relativePath) {
  return readFileSync(new URL(relativePath, APP_ROOT), 'utf8')
    .replace(/\/\*[\s\S]*?\*\//g, '')
    .replace(/(^|\s)\/\/.*$/gm, '$1');
}

const ERROR_BOUNDARIES = ['app/error.tsx', 'app/global-error.tsx'];
const BOUNDARY_FILES = [...ERROR_BOUNDARIES, 'app/not-found.tsx'];

describe('código de producción del tracker', () => {
  test('existen los límites de error y la página no encontrada (y se conserva la de candidates/[id])', () => {
    for (const file of [...BOUNDARY_FILES, 'app/candidates/[id]/not-found.tsx']) {
      assert.ok(PRODUCTION_FILES.includes(file), file);
    }
    for (const file of BOUNDARY_FILES) {
      const code = codeWithoutComments(file);
      assert.doesNotMatch(code, /\berror\s*[.[]/, `${file} lee el error (message, digest, stack…)`);
      assert.match(code, /href=\{HOME_PATH\}/, `${file} sin enlace a inicio`);
    }
    for (const file of ERROR_BOUNDARIES) {
      const code = codeWithoutComments(file);
      assert.match(code, /^'use client';/, `${file} debe ser Client Component`);
      assert.match(code, /onClick=\{\(\) => retry\(\)\}/, `${file} sin «Reintentar» con retry()`);
    }
    const globalError = codeWithoutComments('app/global-error.tsx');
    assert.match(globalError, /<html\b/);
    assert.match(globalError, /<body\b/);
    // No lo envuelven el layout raíz, los avisos ni la sesión: no puede depender de ellos.
    assert.doesNotMatch(globalError, /session-provider|auth-guard|useSession|toast-notification|useToast|app-header/);
  });

  test('nada en components/ ni en app/ muestra error.message, .digest ni hace console.*', () => {
    for (const file of UI_FILES) {
      const code = codeWithoutComments(file);
      for (const [name, pattern] of [
        ['error.message', /\b(error|err|caught)\??\.message\b/],
        ['.digest', /\.digest\b/],
        ['.stack', /\.stack\b/],
        ['console.', /\bconsole\./],
        ['String(error)', /String\(\s*(error|err|caught)\b/],
      ]) {
        assert.equal(pattern.test(code), false, `${file} usa ${name}`);
      }
    }
  });

  test('ningún hook ni servicio convierte un error en texto con String()', () => {
    for (const file of PRODUCTION_FILES) {
      assert.doesNotMatch(codeWithoutComments(file), /new Error\(\s*String\(/, file);
    }
  });

  // El <dialog> de components/ui/modal.tsx no desmonta su contenido al cerrarse:
  // sin una key nueva en cada apertura, el formulario conservaría el bloqueo de
  // reenvío (resubmitBlocked) y los errores del intento anterior.
  test('cada apertura del modal monta un formulario de candidatura nuevo', () => {
    assert.doesNotMatch(codeWithoutComments('components/ui/modal.tsx'), /\{\s*open\s*&&/, 'si el modal desmontara su contenido, esta regla sobraría');
    for (const [file, key, open] of [
      ['components/candidates/candidate-list.tsx', 'createFormKey', 'openCreate'],
      ['components/candidates/candidate-detail.tsx', 'editFormKey', 'openEdit'],
    ]) {
      const code = codeWithoutComments(file);
      assert.match(code, new RegExp(`<CandidateForm\\s+key=\\{${key}\\}`), `${file}: CandidateForm sin key=${key}`);
      assert.match(code, new RegExp(`function ${open}\\(\\) \\{\\s+set\\w+\\(\\(key\\) => key \\+ 1\\);`), `${file}: ${open} no renueva la key`);
      assert.match(code, new RegExp(`onClick=\\{${open}\\}`), `${file}: el botón no abre con ${open}`);
    }
  });

  test('ningún mensaje de error del cliente HTTP lleva el código de estado', () => {
    const client = codeWithoutComments('lib/api-client.ts');
    assert.doesNotMatch(client, /\$\{response\.status\}/);
    assert.doesNotMatch(client, /código/);
  });
});

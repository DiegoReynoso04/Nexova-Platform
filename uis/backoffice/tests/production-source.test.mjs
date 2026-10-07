// Reglas estáticas sobre el código de producción del backoffice (incidentes,
// proveedores y gestor de incidencias; uis/backoffice/CLAUDE.md): `unknown` solo en services/normalizers.ts, nunca
// `any` ni aserciones de tipo, y ninguna API que lea el archivo, persista datos
// o conserve errores originales. Se analiza el código sin comentarios.

import assert from 'node:assert/strict';
import { readFileSync, readdirSync } from 'node:fs';
import { describe, test } from 'node:test';

const APP_ROOT = new URL('../', import.meta.url);
// Todo el código de producción de la app (TS/TSX), incluidos componentes y páginas.
const PRODUCTION_DIRS = ['app', 'components', 'hooks', 'lib', 'services', 'types'];
const PRODUCTION_FILES = PRODUCTION_DIRS.flatMap((dir) =>
  readdirSync(new URL(`${dir}/`, APP_ROOT), { recursive: true })
    .map((entry) => `${dir}/${String(entry).replaceAll('\\', '/')}`)
    .filter((path) => /\.tsx?$/.test(path))
).sort();
const UNKNOWN_ALLOWED_IN = 'services/normalizers.ts';
// Único punto que serializa JSON de salida: los cuerpos de POST/PATCH del
// directorio de proveedores, construidos campo a campo por el servicio.
const JSON_STRINGIFY_ALLOWED_IN = 'lib/api-client.ts';
// AUTH-02: el JWT se guarda en localStorage (exigido por el ticket). Única
// excepción a "sin persistencia en el navegador"; documentada en CLAUDE.md.
const LOCAL_STORAGE_ALLOWED_IN = 'lib/auth-token.ts';

function codeWithoutComments(relativePath) {
  return readFileSync(new URL(relativePath, APP_ROOT), 'utf8')
    .replace(/\/\*[\s\S]*?\*\//g, '')
    .replace(/(^|\s)\/\/.*$/gm, '$1');
}

const FORBIDDEN = [
  ['any', /\bany\b/],
  ['type assertion (as)', /\bas\s+(?!const\b)[A-Za-z_{[(]/],
  ['console.', /\bconsole\./],
  ['FileReader', /\bFileReader\b/],
  ['.text()', /\.text\(\)/],
  ['arrayBuffer(', /arrayBuffer\(/],
  ['sessionStorage', /\bsessionStorage\b/],
  ['indexedDB', /\bindexedDB\b/],
  ['customer_email', /customer_email/],
  ['cause', /\bcause\b/],
  ['originalError', /originalError/],
];

describe('código de producción', () => {
  test('incluye la vista de incidentes y sus piezas', () => {
    for (const file of ['app/incidents/page.tsx', 'components/incidents/incident-analysis-view.tsx', 'hooks/use-incident-analysis.ts']) {
      assert.ok(PRODUCTION_FILES.includes(file), file);
    }
  });

  test('incluye el directorio de proveedores y sus piezas', () => {
    for (const file of [
      'app/suppliers/page.tsx',
      'components/suppliers/supplier-directory-view.tsx',
      'hooks/use-supplier-directory.ts',
      'services/suppliers.service.ts',
    ]) {
      assert.ok(PRODUCTION_FILES.includes(file), file);
    }
  });

  test('incluye el gestor de incidencias y sus piezas', () => {
    for (const file of [
      'app/incident-manager/page.tsx',
      'app/incident-manager/new/page.tsx',
      'components/incident-manager/incident-board-view.tsx',
      'components/incident-manager/incident-form-view.tsx',
      'hooks/use-incident-board.ts',
      'hooks/use-incident-form.ts',
      'hooks/use-incident-summary.ts',
      'services/incident-manager.service.ts',
      'types/incident-manager.ts',
    ]) {
      assert.ok(PRODUCTION_FILES.includes(file), file);
    }
  });

  test('las vistas del gestor son Client Components y sus páginas, Server Components', () => {
    for (const file of ['components/incident-manager/incident-board-view.tsx', 'components/incident-manager/incident-form-view.tsx']) {
      assert.match(codeWithoutComments(file), /^'use client';/, file);
    }
    for (const file of ['app/incident-manager/page.tsx', 'app/incident-manager/new/page.tsx']) {
      const code = codeWithoutComments(file);
      assert.doesNotMatch(code, /'use client'/, file);
      assert.match(code, /export const metadata/, file);
    }
  });

  test('el gestor nunca lee el message de los errores de la API', () => {
    const normalizers = codeWithoutComments('services/normalizers.ts');
    const errorParser = normalizers.slice(normalizers.indexOf('export function normalizeIncidentApiError'));
    assert.ok(errorParser.length > 0);
    assert.doesNotMatch(errorParser, /message/);
  });

  test('el analizador (/incidents) sigue siendo una vista aparte', () => {
    assert.ok(PRODUCTION_FILES.includes('app/incidents/page.tsx'));
    for (const file of PRODUCTION_FILES.filter((path) => path.includes('incident-manager'))) {
      assert.doesNotMatch(codeWithoutComments(file), /use-incident-analysis|incidents\.service/, file);
    }
  });

  // Un elemento `position: absolute` (p. ej. `sr-only`) dentro de un contenedor
  // con overflow que no es su bloque contenedor no queda recortado y ensancha la
  // página: en /incident-manager provocaba scroll horizontal a 375 px. Todo
  // contenedor `overflow-x-auto` de components/ debe llevar `relative`.
  // Excepciones pendientes (mismo patrón, fuera del alcance del arreglo del
  // gestor): si alguna se corrige, hay que quitarla de esta lista.
  const OVERFLOW_WITHOUT_RELATIVE_PENDING = [
    'components/incidents/distribution-table.tsx',
    'components/incidents/invalid-breakdown-table.tsx',
    'components/incidents/satisfaction-panel.tsx',
    'components/suppliers/supplier-table.tsx',
  ];

  test('todo contenedor overflow-x-auto de components/ lleva relative', () => {
    const containers = PRODUCTION_FILES.filter((file) => file.startsWith('components/')).flatMap((file) =>
      [...codeWithoutComments(file).matchAll(/className=(?:"([^"]*)"|\{`([^`]*)`\})/g)]
        .map((match) => match[1] ?? match[2])
        .filter((classes) => /(^|\s)overflow-x-auto(\s|$)/.test(classes))
        .map((classes) => ({ file, relative: /(^|\s)relative(\s|$)/.test(classes) }))
    );
    assert.ok(containers.some((item) => item.file === 'components/incident-manager/incident-table.tsx'));
    for (const { file, relative } of containers) {
      const pending = OVERFLOW_WITHOUT_RELATIVE_PENDING.includes(file);
      assert.equal(relative, !pending, pending ? `${file} ya lleva relative: quítalo de la lista de pendientes` : `${file}: overflow-x-auto sin relative`);
    }
    for (const file of OVERFLOW_WITHOUT_RELATIVE_PENDING) {
      assert.ok(containers.some((item) => item.file === file), `${file} ya no tiene overflow-x-auto: quítalo de la lista`);
    }
  });

  test('incluye las vistas de contraseña (AUTH-03)', () => {
    for (const file of [
      'app/forgot-password/page.tsx',
      'app/reset-password/page.tsx',
      'app/account/change-password/page.tsx',
      'components/auth/forgot-password-view.tsx',
      'components/auth/reset-password-view.tsx',
      'components/auth/change-password-view.tsx',
    ]) {
      assert.ok(PRODUCTION_FILES.includes(file), file);
    }
  });

  test('incluye las vistas y piezas de autenticación (AUTH-02)', () => {
    for (const file of [
      'app/login/page.tsx',
      'app/register/page.tsx',
      'app/account/profile/page.tsx',
      'components/auth/auth-guard.tsx',
      'hooks/use-auth-session.ts',
      'lib/auth-token.ts',
      'services/auth.service.ts',
    ]) {
      assert.ok(PRODUCTION_FILES.includes(file), file);
    }
  });

  test('localStorage solo aparece en lib/auth-token.ts (token de sesión)', () => {
    for (const file of PRODUCTION_FILES) {
      const usesLocalStorage = /\blocalStorage\b/.test(codeWithoutComments(file));
      assert.equal(usesLocalStorage, file === LOCAL_STORAGE_ALLOWED_IN, file);
    }
  });

  test('la cabecera Authorization solo se construye en lib/api-client.ts', () => {
    for (const file of PRODUCTION_FILES) {
      const setsAuthorization = /\bAuthorization\b|\bBearer\b/.test(codeWithoutComments(file));
      assert.equal(setsAuthorization, file === 'lib/api-client.ts', file);
    }
  });

  test('JSON.stringify solo aparece en lib/api-client.ts', () => {
    for (const file of PRODUCTION_FILES) {
      const stringifies = /JSON\.stringify/.test(codeWithoutComments(file));
      assert.equal(stringifies, file === JSON_STRINGIFY_ALLOWED_IN, file);
    }
  });

  test('la UI no puede eliminar proveedores (sin DELETE ni borrado en el cliente)', () => {
    for (const file of PRODUCTION_FILES) {
      const code = codeWithoutComments(file);
      assert.equal(/['"]DELETE['"]/.test(code), false, `${file} issues DELETE`);
      assert.equal(/deleteSupplier|removeSupplier|Eliminar/i.test(code), false, `${file} exposes deletion`);
    }
  });

  for (const file of PRODUCTION_FILES) {
    test(`${file} no usa construcciones prohibidas`, () => {
      const code = codeWithoutComments(file);
      for (const [name, pattern] of FORBIDDEN) {
        assert.equal(pattern.test(code), false, `${file} contains ${name}`);
      }
    });
  }

  test('unknown solo aparece en services/normalizers.ts', () => {
    for (const file of PRODUCTION_FILES) {
      const hasUnknown = /\bunknown\b/.test(codeWithoutComments(file));
      assert.equal(hasUnknown, file === UNKNOWN_ALLOWED_IN, file);
    }
  });

  test('lib/api-client.ts no contiene unknown ni any', () => {
    const code = codeWithoutComments('lib/api-client.ts');
    assert.equal(/\bunknown\b/.test(code), false);
    assert.equal(/\bany\b/.test(code), false);
  });

  test('el único fetch de red está en lib/api-client.ts', () => {
    for (const file of PRODUCTION_FILES) {
      const callsFetch = /\bfetch\(/.test(codeWithoutComments(file));
      assert.equal(callsFetch, file === 'lib/api-client.ts', file);
    }
  });
});

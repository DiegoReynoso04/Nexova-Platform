// Reglas estáticas sobre el código de producción del backoffice (incidentes,
// proveedores, gestor de incidencias e inventario; uis/backoffice/CLAUDE.md): `unknown` solo en services/normalizers.ts, nunca
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

  test('incluye la integración del inventario (Hito 5)', () => {
    for (const file of [
      'lib/inventory-api-client.ts',
      'lib/inventory-routes.ts',
      'services/inventory.service.ts',
      'types/inventory.ts',
    ]) {
      assert.ok(PRODUCTION_FILES.includes(file), file);
    }
  });

  test('el inventario usa su propio cliente, sin reserva a NEXT_PUBLIC_API_URL', () => {
    const client = codeWithoutComments('lib/inventory-api-client.ts');
    assert.match(client, /process\.env\.NEXT_PUBLIC_INVENTORY_API_URL/);
    assert.doesNotMatch(client, /NEXT_PUBLIC_API_URL/);
    const service = codeWithoutComments('services/inventory.service.ts');
    assert.match(service, /inventoryApiClient/);
    assert.doesNotMatch(service, /\bapiClient\b/);
    // Ningún otro módulo nombra las rutas de la API: el servicio lo centraliza.
    // lib/inventory-routes.ts se excluye: las páginas del brief se llaman igual
    // que las rutas de la API, pero son rutas de navegación, no peticiones. Por
    // lo mismo se ignora el argumento de `PageProps<'…'>`/`LayoutProps<'…'>`:
    // es el tipo de ruta que genera Next para las props de una página, no una URL.
    const allowed = ['services/inventory.service.ts', 'lib/inventory-routes.ts'];
    for (const file of PRODUCTION_FILES.filter((path) => !allowed.includes(path))) {
      const code = codeWithoutComments(file).replace(/\b(PageProps|LayoutProps)<'[^']*'>/g, '$1<>');
      assert.doesNotMatch(code, /['`]\/inventory\/(products|orders)['`/]/, file);
    }
  });

  test('incluye la página de activos del inventario y su navegación (F2)', () => {
    for (const file of [
      'app/inventory/layout.tsx',
      'app/inventory/page.tsx',
      'app/inventory/products/page.tsx',
      'components/inventory/asset-list-view.tsx',
      'components/inventory/asset-table.tsx',
      'components/inventory/inventory-error.tsx',
      'components/inventory/inventory-nav.tsx',
      'components/inventory/stock-level-badge.tsx',
      'hooks/use-inventory-assets.ts',
      'lib/inventory-error-copy.ts',
      'lib/stock-level.ts',
    ]) {
      assert.ok(PRODUCTION_FILES.includes(file), file);
    }
  });

  test('las páginas del inventario son Server Components; sus vistas, Client Components que solo usan hooks', () => {
    for (const file of PRODUCTION_FILES.filter((path) => path.startsWith('app/inventory/'))) {
      assert.doesNotMatch(codeWithoutComments(file), /^'use client';/, `${file} debe ser Server Component`);
    }
    assert.match(codeWithoutComments('app/inventory/products/page.tsx'), /export const metadata/);
    for (const file of PRODUCTION_FILES.filter((path) => /^components\/inventory\/.+-view\.tsx$/.test(path))) {
      const code = codeWithoutComments(file);
      assert.match(code, /^'use client';/, `${file} debe ser Client Component`);
      assert.match(code, /from '@\/hooks\/use-inventory-/, `${file} sin su hook`);
    }
    for (const file of PRODUCTION_FILES.filter((path) => path.startsWith('components/inventory/') || path.startsWith('app/inventory/'))) {
      assert.doesNotMatch(codeWithoutComments(file), /services\/inventory\.service/, `${file} llama al servicio sin pasar por su hook`);
    }
  });

  test('/inventory redirige a Activos y el layout lleva la subnavegación', () => {
    const index = codeWithoutComments('app/inventory/page.tsx');
    assert.match(index, /import \{ redirect \} from 'next\/navigation'/);
    assert.match(index, /redirect\(INVENTORY_PRODUCTS_PATH\)/);
    assert.match(codeWithoutComments('app/inventory/layout.tsx'), /<InventoryNav \/>/);
    const nav = codeWithoutComments('components/inventory/inventory-nav.tsx');
    for (const label of ['Activos', 'Entrada de activos', 'Salida de activos', 'Historial']) {
      assert.match(nav, new RegExp(`label: '${label}'`), label);
    }
    assert.match(nav, /<NavLink /);
  });

  test('la cabecera lleva un solo enlace «Inventario», activo en todo /inventory', () => {
    const header = codeWithoutComments('components/auth/account-nav.tsx');
    assert.match(header, /<NavLink href=\{INVENTORY_PRODUCTS_PATH\} activePrefix=\{INVENTORY_PATH\}>\s*Inventario\s*<\/NavLink>/);
    assert.equal((header.match(/INVENTORY_[A-Z_]+_PATH\}/g) ?? []).length, 1);
    assert.doesNotMatch(header, /Entrada de activos|Salida de activos|Historial/);
  });

  test('cada fila de activos enlaza a registrar una entrada y una salida de ese activo', () => {
    const table = codeWithoutComments('components/inventory/asset-table.tsx');
    assert.match(table, /href=\{inboundOrderHref\(asset\.id\)\}[^>]*>\s*Registrar entrada/);
    assert.match(table, /href=\{outboundOrderHref\(asset\.id\)\}[^>]*>\s*Registrar salida/);
    for (const column of ['Nombre', 'SKU', 'Categoría', 'Oficina', 'Stock actual']) {
      assert.match(table, new RegExp(`>${column}</th>`), column);
    }
    assert.match(table, /<StockLevelBadge currentStock=\{asset\.current_stock\} \/>/);
  });

  test('incluye la entrada de activos y sus piezas (F3)', () => {
    for (const file of [
      'app/inventory/orders/inbound/page.tsx',
      'components/inventory/asset-select.tsx',
      'components/inventory/field-messages.tsx',
      'components/inventory/inbound-form-view.tsx',
      'components/inventory/inbound-form.tsx',
      'components/inventory/read-only-field.tsx',
      'hooks/use-inbound-form.ts',
      'lib/asset-preselection.ts',
      'lib/inventory-form-errors.ts',
    ]) {
      assert.ok(PRODUCTION_FILES.includes(file), file);
    }
  });

  test('el selector de activo muestra «nombre — SKU (oficina)», nunca el id', () => {
    const select = codeWithoutComments('components/inventory/asset-select.tsx');
    assert.match(select, /<option key=\{asset\.id\} value=\{String\(asset\.id\)\}>\s*\{assetOptionLabel\(asset\)\}\s*<\/option>/);
    // Ningún texto visible de una opción menciona un id.
    const options = [...select.matchAll(/<option\b[^>]*>([^<]*)<\/option>/g)];
    assert.ok(options.length >= 4, 'opciones del selector');
    for (const [, text] of options) assert.doesNotMatch(text, /\bid\b/i, text);
    const preselection = codeWithoutComments('lib/asset-preselection.ts');
    const label = preselection.slice(preselection.indexOf('export function assetOptionLabel'));
    assert.match(label, /^export function assetOptionLabel\(asset: Pick<Asset, 'name' \| 'sku' \| 'office'>\): string \{\s*return `\$\{asset\.name\} — \$\{asset\.sku\} \(\$\{asset\.office\}\)`;/);
  });

  test('la vista de entrada solo usa sus hooks; ni fetch ni cliente HTTP en las piezas del inventario', () => {
    const view = codeWithoutComments('components/inventory/inbound-form-view.tsx');
    assert.match(view, /from '@\/hooks\/use-inbound-form'/);
    assert.match(view, /from '@\/hooks\/use-inventory-assets'/);
    for (const file of PRODUCTION_FILES.filter((path) => path.startsWith('components/inventory/') || path.startsWith('app/inventory/'))) {
      const code = codeWithoutComments(file);
      assert.doesNotMatch(code, /\bfetch\b/, `${file} hace HTTP`);
      assert.doesNotMatch(code, /lib\/(inventory-)?api-client/, `${file} usa el cliente HTTP`);
    }
    const hook = codeWithoutComments('hooks/use-inbound-form.ts');
    assert.match(hook, /from '@\/services\/inventory\.service'/);
    assert.doesNotMatch(hook, /\bfetch\b|inventory-api-client|inventoryApiClient/);
  });

  test('entrada: oficina del activo en solo lectura, botón con carga y formulario limpio con formKey', () => {
    const form = codeWithoutComments('components/inventory/inbound-form.tsx');
    // La oficina es un valor de solo lectura (<output>), no un control editable.
    assert.match(
      form,
      /<ReadOnlyField\s+id="inbound-office"\s+label="Oficina"\s+value=\{selected\?\.office \?\? null\}\s+placeholder="Se toma del activo elegido"\s+help="La oficina receptora es la del activo[^"]*"/
    );
    assert.doesNotMatch(form, /id="inbound-office"[^>]*onChange|<input\s+id="inbound-office"/);
    const readOnly = codeWithoutComments('components/inventory/read-only-field.tsx');
    assert.match(readOnly, /<label htmlFor=\{id\}/);
    assert.match(readOnly, /<output id=\{id\}/);
    assert.doesNotMatch(readOnly, /<input|<select|<textarea|\bborder\b|onChange/);
    assert.match(form, /asset: selected === null \? null : \{ id: selected\.id, office: selected\.office \}/);
    assert.match(form, /<Button type="submit" isLoading=\{isSubmitting\}>/);
    const view = codeWithoutComments('components/inventory/inbound-form-view.tsx');
    assert.match(view, /<InboundForm\s+key=\{`\$\{formKey\}-\$\{preselection\.status\}`\}/);
    // Tras el éxito, el formulario limpio conserva el activo de la URL.
    assert.match(view, /initialAssetId=\{formInitialAssetId\(preselection\)\}/);
  });

  test('incluye la salida de activos y sus piezas (F4)', () => {
    for (const file of [
      'app/inventory/orders/outbound/page.tsx',
      'components/inventory/outbound-form-view.tsx',
      'components/inventory/outbound-form.tsx',
      'hooks/use-outbound-form.ts',
      'lib/stock-check.ts',
    ]) {
      assert.ok(PRODUCTION_FILES.includes(file), file);
    }
  });

  test('salida: la vista solo usa sus hooks y elige el activo de la URL, también tras el éxito', () => {
    const view = codeWithoutComments('components/inventory/outbound-form-view.tsx');
    assert.match(view, /from '@\/hooks\/use-outbound-form'/);
    assert.match(view, /from '@\/hooks\/use-inventory-assets'/);
    assert.match(view, /const initialAssetId = formInitialAssetId\(preselection\);/);
    assert.match(view, /if \(initialAssetId !== null\) selectAsset\(initialAssetId\);/);
    assert.match(view, /submitOutbound\(values, initialAssetId\)/);
    assert.match(view, /<OutboundForm\s+key=\{formKey\}/);
    const hook = codeWithoutComments('hooks/use-outbound-form.ts');
    assert.match(hook, /from '@\/services\/inventory\.service'/);
    assert.doesNotMatch(hook, /\bfetch\b|inventory-api-client|inventoryApiClient/);
  });

  test('salida: selector compartido, Stock actual antes que Cantidad y la oficina en solo lectura', () => {
    const form = codeWithoutComments('components/inventory/outbound-form.tsx');
    assert.match(form, /<AssetSelect\s+id="outbound-asset"/);
    assert.doesNotMatch(form, /<option\b/);
    const order = ['id="outbound-asset"', 'id="outbound-stock"', 'id="outbound-office"', 'Tipo de salida *', 'id="outbound-assigned-to"', 'id="outbound-quantity"'];
    const positions = order.map((marker) => form.indexOf(marker));
    assert.ok(positions.every((position) => position >= 0), String(positions));
    assert.deepEqual([...positions].sort((a, b) => a - b), positions, 'orden de los campos');
    assert.match(form, /<ReadOnlyField\s+id="outbound-stock"\s+label="Stock actual"/);
    assert.match(
      form,
      /<ReadOnlyField\s+id="outbound-office"\s+label="Oficina"\s+value=\{selected\?\.office \?\? null\}\s+placeholder="Se toma del activo elegido"/
    );
    assert.doesNotMatch(form, /<input\s+id="outbound-(office|stock)"/);
    // Se envía la oficina del activo elegido.
    assert.match(form, /outboundFormValues\(selected === null \? null : \{ id: selected\.id, office: selected\.office \}/);
  });

  test('salida: Cantidad espera al stock, advertencia sin bloqueo y el 400 de stock bajo Cantidad', () => {
    const form = codeWithoutComments('components/inventory/outbound-form.tsx');
    assert.match(form, /disabled=\{isSubmitting \|\| !quantityEnabled\(stock\)\}/);
    assert.match(form, /<div id="outbound-quantity-warning" aria-live="polite">/);
    assert.match(form, /Consultando stock…/);
    assert.match(form, /No se pudo consultar el stock/);
    assert.match(form, /<FieldMessages id="outbound-quantity-messages" messages=\{quantityMessages\} alert=\{error\?\.kind === 'api_error'\} \/>/);
    assert.match(codeWithoutComments('components/inventory/field-messages.tsx'), /role=\{alert \? 'alert' : undefined\}/);
    // La advertencia nunca decide si se envía.
    const submit = form.slice(form.indexOf('function handleSubmit'), form.indexOf('const summaryRef'));
    assert.doesNotMatch(submit, /showWarning|exceedsStock|currentStock/);
    // «Asignado a» solo existe con una asignación.
    assert.match(form, /\{exitType === 'allocation' && \(\s*<div className="flex flex-col gap-1">\s*<label htmlFor="outbound-assigned-to"/);
    assert.match(form, /value: 'allocation', label: 'Asignación'/);
    assert.match(form, /value: 'consumption', label: 'Consumo'/);
    assert.match(form, /<Button type="submit" isLoading=\{isSubmitting\}>/);
  });

  test('la UI del inventario usa el vocabulario del CONTEXT («activos», no «productos»)', () => {
    for (const file of PRODUCTION_FILES.filter((path) => path.startsWith('components/inventory/') || path.startsWith('app/inventory/'))) {
      assert.doesNotMatch(codeWithoutComments(file), /\b[Pp]roductos?\b/, file);
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

  // B1 de la auditoría de gestión de errores: límites de error de Next 16.
  const ERROR_BOUNDARIES = ['app/error.tsx', 'app/global-error.tsx'];
  const BOUNDARY_FILES = [...ERROR_BOUNDARIES, 'app/not-found.tsx'];

  test('existen los límites de error y la página no encontrada, sin consola ni datos del error', () => {
    for (const file of BOUNDARY_FILES) {
      assert.ok(PRODUCTION_FILES.includes(file), file);
      const code = codeWithoutComments(file);
      assert.doesNotMatch(code, /\bconsole\./, `${file} usa console`);
      assert.doesNotMatch(code, /\berror\s*[.[]/, `${file} lee el error (message, digest, stack…)`);
      assert.doesNotMatch(code, /\.(message|digest|stack)\b/, `${file} muestra message, digest o stack`);
      assert.match(code, /href=\{HOME_PATH\}/, `${file} sin enlace a la página principal`);
    }
    for (const file of ERROR_BOUNDARIES) {
      const code = codeWithoutComments(file);
      assert.match(code, /^'use client';/, `${file} debe ser Client Component`);
      assert.match(code, /onClick=\{\(\) => retry\(\)\}/, `${file} sin «Reintentar» con retry()`);
      assert.match(code, /Reintentar/, file);
    }
    const globalError = codeWithoutComments('app/global-error.tsx');
    assert.match(globalError, /<html\b/);
    assert.match(globalError, /<body\b/);
    // No lo envuelven el layout raíz ni la sesión: no puede depender de ellos.
    assert.doesNotMatch(globalError, /session-provider|auth-guard|useSession|account-nav/);
  });

  // B2: el usuario no ve detalles técnicos (variables de entorno, rutas del
  // repositorio ni códigos HTTP entre paréntesis) en ningún texto de la UI.
  test('ningún texto de components/ ni app/ muestra detalles técnicos', () => {
    for (const file of PRODUCTION_FILES.filter((path) => path.startsWith('components/') || path.startsWith('app/'))) {
      const code = codeWithoutComments(file);
      for (const [name, pattern] of [
        ['NEXT_PUBLIC_', /NEXT_PUBLIC_/],
        ['services/api', /services\/api/],
        ['código HTTP entre paréntesis', /\([1-5]\d\d\)/],
      ]) {
        assert.equal(pattern.test(code), false, `${file} muestra ${name}`);
      }
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

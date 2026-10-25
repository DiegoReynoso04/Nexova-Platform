// next.config.ts (#infra-40): el rewrite de /backend/* a la API dentro de Docker.
// El módulo lee API_INTERNAL_URL al importarse, así que cada caso lo importa de
// nuevo con una query distinta (Node crea otro módulo) y restaura process.env.

import assert from 'node:assert/strict';
import { describe, test } from 'node:test';

let importCount = 0;

/** Importa next.config.ts con API_INTERNAL_URL = value (undefined: sin definir) y deja process.env como estaba. */
async function loadConfig(value) {
  const previous = process.env.API_INTERNAL_URL;
  if (value === undefined) delete process.env.API_INTERNAL_URL;
  else process.env.API_INTERNAL_URL = value;
  try {
    importCount += 1;
    const imported = await import(`../next.config.ts?case=${importCount}`);
    return imported.default;
  } finally {
    if (previous === undefined) delete process.env.API_INTERNAL_URL;
    else process.env.API_INTERNAL_URL = previous;
  }
}

describe('next.config.ts: rewrite de /backend a la API (Docker)', () => {
  test('sin API_INTERNAL_URL no hay rewrites: el backoffice funciona como fuera de Docker', async () => {
    const config = await loadConfig(undefined);
    assert.deepEqual(await config.rewrites(), []);
  });

  test('con una cadena vacía o solo espacios, tampoco', async () => {
    for (const value of ['', '   ']) {
      const config = await loadConfig(value);
      assert.deepEqual(await config.rewrites(), [], JSON.stringify(value));
    }
  });

  test('con http://api:8000, /backend/:path* va a la API por nombre de servicio', async () => {
    const config = await loadConfig('http://api:8000');
    assert.deepEqual(await config.rewrites(), [{ source: '/backend/:path*', destination: 'http://api:8000/:path*' }]);
  });

  test('las barras finales y los espacios se normalizan', async () => {
    for (const value of ['http://api:8000/', 'http://api:8000///', '  http://api:8000/  ']) {
      const config = await loadConfig(value);
      assert.deepEqual(
        await config.rewrites(),
        [{ source: '/backend/:path*', destination: 'http://api:8000/:path*' }],
        JSON.stringify(value)
      );
    }
  });

  test('la config no lleva watchOptions: la recarga en Docker es de Watchpack (WATCHPACK_POLLING)', async () => {
    const config = await loadConfig('http://api:8000');
    assert.equal('watchOptions' in config, false);
  });

  test('importar la config no deja API_INTERNAL_URL cambiada para otros tests', async () => {
    const before = process.env.API_INTERNAL_URL;
    await loadConfig('http://api:8000');
    assert.equal(process.env.API_INTERNAL_URL, before);
  });
});

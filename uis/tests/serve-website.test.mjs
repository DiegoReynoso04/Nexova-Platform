// uis/serve-website.mjs (#infra-40): resolución de rutas del servidor estático
// del website. Ninguna petición puede salir de uis/website.
//
// Desde la raíz del monorepo (Node 24, sin dependencias):
//   node --test "uis/tests/*.test.mjs"

import assert from 'node:assert/strict';
import path from 'node:path';
import { describe, test } from 'node:test';
import { fileURLToPath } from 'node:url';

import { resolveRequestPath } from '../serve-website.mjs';

const WEBSITE = path.join(path.dirname(fileURLToPath(import.meta.url)), '..', 'website');

describe('serve-website.mjs: rutas dentro de uis/website', () => {
  test('"/" sirve index.html', () => {
    assert.equal(resolveRequestPath('/'), path.join(WEBSITE, 'index.html'));
  });

  test('los archivos se sirven tal cual, con su extensión', () => {
    assert.equal(resolveRequestPath('/index.html'), path.join(WEBSITE, 'index.html'));
    assert.equal(resolveRequestPath('/application.html'), path.join(WEBSITE, 'application.html'));
    assert.equal(resolveRequestPath('/src/img/logo.svg'), path.join(WEBSITE, 'src', 'img', 'logo.svg'));
  });

  test('la query y el fragmento no forman parte de la ruta', () => {
    assert.equal(resolveRequestPath('/application.html?ref=nav#form'), path.join(WEBSITE, 'application.html'));
    assert.equal(resolveRequestPath('/?utm=x'), path.join(WEBSITE, 'index.html'));
  });
});

describe('serve-website.mjs: ninguna ruta sale de uis/website', () => {
  test('las siete variantes de ".." de F3 se rechazan', () => {
    for (const url of [
      '/..%2f..%2f.env',
      '/%2e%2e/%2e%2e/.env',
      '/../../.env',
      '/..%5c..%5c.env',
      '/%2e%2e%2f%2e%2e%2fbackoffice/package.json',
      '/index.html%00.png',
      '/src/..%2f..%2fstart.sh',
    ]) {
      assert.equal(resolveRequestPath(url), null, url);
    }
  });

  test('cualquier ".." se rechaza, aunque la ruta resultante siga dentro de uis/website', () => {
    for (const url of ['/src/../index.html', '/src/%2e%2e/index.html']) {
      assert.equal(resolveRequestPath(url), null, url);
    }
  });

  test('una barra invertida se rechaza, literal o codificada', () => {
    for (const url of ['/src\\img\\logo.svg', '/src%5cimg%5clogo.svg']) {
      assert.equal(resolveRequestPath(url), null, url);
    }
  });

  test('un byte nulo se rechaza', () => {
    for (const url of ['/index.html%00', '/%00']) {
      assert.equal(resolveRequestPath(url), null, url);
    }
  });

  test('una codificación inválida se rechaza sin lanzar', () => {
    for (const url of ['/%E0%A4%A', '/%', '/%zz']) {
      assert.equal(resolveRequestPath(url), null, url);
    }
  });
});

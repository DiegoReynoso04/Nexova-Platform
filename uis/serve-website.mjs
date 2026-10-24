// Servidor estático de uis/website para el contenedor de interfaces (#infra-40).
//
// uis/website es HTML estático sin build que publica Netlify (netlify.toml), así
// que este archivo vive fuera de esa carpeta. Solo usa módulos de Node (http,
// fs y path): sin dependencias. La busybox de la imagen Alpine no trae httpd.
//
// - "/" sirve index.html; el resto de rutas, el archivo tal cual (los enlaces
//   del website llevan extensión: index.html, application.html).
// - Una ruta inexistente responde 404.html con estado 404.
// - Ninguna ruta puede salir de uis/website: se rechazan "..", barras
//   invertidas y bytes nulos, también codificados (%2e%2e, %5c, %00).
// - Solo GET y HEAD; el resto, 405.
// - El archivo se lee en cada petición, sin caché, para que un cambio en el
//   host se vea al recargar el navegador.

import { readFile, stat } from 'node:fs/promises';
import { createServer } from 'node:http';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const HOST = '0.0.0.0';
const PORT = 3000;
const ROOT = path.join(path.dirname(fileURLToPath(import.meta.url)), 'website');
const NOT_FOUND_PAGE = path.join(ROOT, '404.html');

const CONTENT_TYPES = {
  '.html': 'text/html; charset=utf-8',
  '.css': 'text/css; charset=utf-8',
  '.js': 'text/javascript; charset=utf-8',
  '.mjs': 'text/javascript; charset=utf-8',
  '.json': 'application/json; charset=utf-8',
  '.svg': 'image/svg+xml',
  '.jpg': 'image/jpeg',
  '.jpeg': 'image/jpeg',
  '.png': 'image/png',
  '.ico': 'image/x-icon',
  '.webp': 'image/webp',
  '.txt': 'text/plain; charset=utf-8',
};

/**
 * Ruta del archivo pedido dentro de ROOT, o `null` si la petición no es válida
 * o intentaría salir de ROOT.
 */
function resolveRequestPath(rawUrl) {
  const pathname = rawUrl.split('?', 1)[0].split('#', 1)[0];
  let decoded;
  try {
    decoded = decodeURIComponent(pathname);
  } catch {
    return null;
  }
  if (decoded.includes('\0') || decoded.includes('\\')) return null;
  if (decoded.split('/').includes('..')) return null;
  const relative = decoded === '/' ? 'index.html' : decoded.replace(/^\/+/, '');
  const resolved = path.resolve(ROOT, relative);
  return resolved.startsWith(ROOT + path.sep) ? resolved : null;
}

async function readRegularFile(filePath) {
  const info = await stat(filePath);
  if (!info.isFile()) throw new Error('not a file');
  return readFile(filePath);
}

function send(request, response, status, body, contentType) {
  response.writeHead(status, {
    'Content-Type': contentType,
    'Content-Length': body.length,
    'Cache-Control': 'no-store',
    'X-Content-Type-Options': 'nosniff',
  });
  response.end(request.method === 'HEAD' ? undefined : body);
}

async function sendNotFound(request, response) {
  try {
    send(request, response, 404, await readFile(NOT_FOUND_PAGE), CONTENT_TYPES['.html']);
  } catch {
    send(request, response, 404, Buffer.from('Not found\n'), CONTENT_TYPES['.txt']);
  }
}

const server = createServer(async (request, response) => {
  if (request.method !== 'GET' && request.method !== 'HEAD') {
    response.setHeader('Allow', 'GET, HEAD');
    send(request, response, 405, Buffer.from('Method not allowed\n'), CONTENT_TYPES['.txt']);
    return;
  }
  const filePath = resolveRequestPath(request.url ?? '/');
  if (filePath === null) {
    await sendNotFound(request, response);
    return;
  }
  try {
    const body = await readRegularFile(filePath);
    const contentType = CONTENT_TYPES[path.extname(filePath).toLowerCase()] ?? 'application/octet-stream';
    send(request, response, 200, body, contentType);
  } catch {
    await sendNotFound(request, response);
  }
});

server.listen(PORT, HOST, () => {
  console.log(`website: http://${HOST}:${PORT} (sirve ${ROOT})`);
});

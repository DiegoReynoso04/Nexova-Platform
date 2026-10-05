// Solo para tests: resuelve el alias `@/…` de tsconfig.json a los archivos .ts de
// esta app, para que `node --test` pueda cargar módulos de producción que se
// importan entre sí con el alias (igual que en Next.js). Usa únicamente la API
// nativa `module.registerHooks` de Node; no cambia tsconfig ni la config de Next.
//
//   node --import ./tests/support/resolve-alias.mjs --test "tests/*.test.mjs"

import { existsSync } from 'node:fs';
import { registerHooks } from 'node:module';
import { fileURLToPath } from 'node:url';

const APP_ROOT = new URL('../../', import.meta.url);
const EXTENSIONS = ['.ts', '.tsx'];

registerHooks({
  resolve(specifier, context, nextResolve) {
    if (!specifier.startsWith('@/')) return nextResolve(specifier, context);
    const base = new URL(specifier.slice(2), APP_ROOT);
    for (const extension of EXTENSIONS) {
      const candidate = new URL(`${base.href}${extension}`);
      if (existsSync(fileURLToPath(candidate))) return nextResolve(candidate.href, context);
    }
    return nextResolve(base.href, context);
  },
});

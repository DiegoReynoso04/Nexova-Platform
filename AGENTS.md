# AGENTS.md — Nexova Monorepo

Flujo operativo obligatorio para cualquier agente de IA que trabaje en este repositorio. Reglas granulares en [`.agents/rules/`](./.agents/rules/); skills reutilizables en [`.agents/skills/`](./.agents/skills/).

## 1. Antes de tocar nada

Leer, en este orden:

1. [`memory-bank/projectbrief.md`](./memory-bank/projectbrief.md) — quién es Nexova, qué se ha construido, quién lo pidió.
2. [`memory-bank/techContext.md`](./memory-bank/techContext.md) — stacks reales, decisiones de arquitectura vigentes.
3. [`memory-bank/progress.md`](./memory-bank/progress.md) — qué está hecho, qué está en curso, problemas conocidos.

Para el briefing de negocio completo (no el resumen), leer `contexts/CONTEXT.md` **si existe en tu checkout** — esa carpeta está en `.gitignore` y no viaja con el repositorio (ver nota en `techContext.md`). Si no la tienes, el `README.md` raíz contiene ese mismo briefing (copia versionada desde el 2026-09-27). No existe ningún `CONTEXT.md` en la raíz.

## 2. Antes de trabajar en una carpeta concreta

Leer el `README.md` de esa carpeta de primer nivel (`uis/README.md`, `services/README.md`, etc. — ver `.agents/rules/monorepo-structure.md`) y, si el subproyecto tiene su propia documentación (`CLAUDE.md`, `AGENTS.md`, `SPECS.md` — por ejemplo `uis/talent-pipeline-tracker/`), leerla también.

**Las reglas locales de una app priman sobre las de este archivo dentro de su propio árbol** (ver `.agents/rules/app-specific-overrides.md`), nunca al revés.

## 3. Reglas duras (detalle en `.agents/rules/`)

- No inventar datos de negocio sobre Nexova ni campos/endpoints/estructuras de API que no estén documentados o verificados.
- No crear una app, servicio o carpeta fuera del lugar que le corresponde según la convención de carpetas de [`.agents/rules/monorepo-structure.md`](./.agents/rules/monorepo-structure.md) y el `README.md` de la carpeta destino.
- No añadir dependencias nuevas a ningún subproyecto sin autorización explícita.
- No duplicar en `.agents/` ni en `memory-bank/` lo que ya documenta un `SPECS.md`/`CLAUDE.md` propio de una app — referenciar, no copiar.
- Al cerrar cualquier tarea que modifique archivos del repo — **haya commit o no** — aplicar la skill [`memory-bank-sync`](./.agents/skills/memory-bank-sync/SKILL.md): `progress.md` siempre; `techContext.md` solo si cambió algo técnico; `projectbrief.md` solo si cambió algo de negocio. Tareas de solo lectura no tocan `memory-bank/`.

## 4. Flujo antes de commit (obligatorio, en este orden)

Ningún agente commitea código sin completar estos cinco pasos, en orden:

1. **Ejecutar la validación del subproyecto tocado.** Este monorepo **no** tiene un comando único de verificación — cada subproyecto valida el suyo:

   | Subproyecto | Comando |
   |---|---|
   | `src/` (Hito 2 — domain models) | `npm run check` (typecheck + tests) |
   | `uis/talent-pipeline-tracker/` | Desde `uis/talent-pipeline-tracker`: `npx tsc --noEmit` + `npm run lint` (hoy con 4 errores `react-hooks/set-state-in-effect` anteriores a AUTH-02 en `use-notes`/`use-record-detail`/`use-records`) + tests con Node 24: `node --disable-warning=MODULE_TYPELESS_PACKAGE_JSON --import ./tests/support/resolve-alias.mjs --test --test-timeout=10000 "tests/*.test.mjs"` |
   | `uis/backoffice/` | Desde `uis/backoffice`: `npx tsc --noEmit` + `npm run lint` + `npm run build` + tests con Node 24: `node --disable-warning=MODULE_TYPELESS_PACKAGE_JSON --import ./tests/support/resolve-alias.mjs --test --test-timeout=10000 "tests/*.test.mjs"` |
   | `uis/website/` | sin build step — verificación manual/visual |
   | `packages/incident-analyzer/` + `scripts/analyze.py` | `python -m unittest discover -s packages/incident-analyzer/tests -t packages/incident-analyzer` (desde la raíz) |
   | `services/api/` | **Requiere el venv del servicio** (con el Python global falla al importar `fastapi`). Desde la raíz, sin activar nada: `services\api\.venv\Scripts\python -m unittest discover -s services/api/tests -t services/api` (Windows) o `services/api/.venv/bin/python -m unittest discover -s services/api/tests -t services/api` (Linux/macOS). Crear/instalar el venv: ver `services/api/README.md` |

   Si el cambio afecta a más de un subproyecto, ejecutar todos los comandos que correspondan.

   **Procesador de incidentes de Nexova — Fase 3 (`uis/backoffice`, ruta `/incidents`, implementada):** Server Component que renderiza una vista cliente; la vista solo interactúa mediante el hook `hooks/use-incident-analysis.ts` (frontera de interacción) → `services/incidents.service.ts` → `lib/api-client.ts` (único `fetch`) → `services/api`. `unknown` de red solo en `services/normalizers.ts`. Privacidad: el frontend no lee el contenido del CSV ni muestra `customer_email` o datos de filas. Además de la validación de la tabla, un cambio en `/incidents` se verifica manualmente en el navegador (descarga, exportación obsoleta, cancelación al salir). Reglas completas en `uis/backoffice/CLAUDE.md`; no se duplican aquí.

   **Autenticación AUTH-01 (`services/api` → `/auth`, `/users`, `/profiles`):** contexto en `docs/auth-api.md`; contrato en `services/api/SPECS.md` Parte C. La API no arranca sin `JWT_SECRET_KEY` y `ACCESS_TOKEN_EXPIRE_MINUTES` (en `services/api/.env`, ignorado por git; nunca en el código). La suite de `services/api` cubre AUTH-01 y comprueba que las rutas de incidentes y proveedores exigen token; un cambio en auth se verifica también en `/docs` (registro → *Authorize* → ruta protegida; sin token → 401). `User`/`Profile` viven solo en TinyDB.

   **Autenticación en el frontend AUTH-02 (`uis/backoffice` y `uis/talent-pipeline-tracker`; `uis/website` sigue público):** contexto en `docs/auth-frontend.md`. Token en `localStorage` (único módulo `lib/auth-token.ts` por app), `Authorization: Bearer` y 401 solo en `lib/api-client.ts`, guard global en el layout raíz (sin middleware ni cookies). Para probar en local: `services/api` en marcha con `CORS_ALLOWED_ORIGINS=http://localhost:3000,http://localhost:3001` (backoffice en 3000, tracker en 3001). Un cambio de autenticación se verifica también en el navegador (login correcto/incorrecto, registro con 422, perfil, redirección sin token y tras 401, logout). Reglas en el `CLAUDE.md` de cada app y en `uis/talent-pipeline-tracker/SPECS.md` §9.

   **Directorio de proveedores de Nexova (`services/api` → `/suppliers`, `uis/backoffice` → `/suppliers`):** contexto en `docs/ligthweight-storage-api.md`; contrato en `services/api/SPECS.md` Parte B. La validación de `services/api` de la tabla cubre también los tests de proveedores; además, `cd services/api && uv run seed` debe ejecutarse sin errores y ser idempotente. Un cambio en `/suppliers` se verifica también en el navegador (filtros, alta con 422, tarifa, estado).

2. **Revisar el diff real antes de comitear:** `git status --short` y `git diff --stat`. Confirmar que no se incluyen archivos generados (`node_modules/`, `.next/`, `*.log`, `*.tsbuildinfo`) ni dependencias no autorizadas en ningún `package.json` tocado.

3. **Confirmar fidelidad al contexto de negocio:** ningún dato nuevo sobre Nexova (nombre, cifra, responsable, proceso) queda sin respaldo en `contexts/CONTEXT.md` (si existe localmente), el `README.md` raíz, un documento de contexto de `docs/` o `memory-bank/projectbrief.md` — ver `.agents/rules/nexova-context.md`.

4. **Sincronizar el banco de memoria:** aplicar la skill [`memory-bank-sync`](./.agents/skills/memory-bank-sync/SKILL.md) — actualizar `progress.md` (y `techContext.md`/`projectbrief.md` si corresponde). Sin esto, el banco de memoria queda desactualizado en días y la siguiente sesión de agente vuelve a empezar de cero.

5. **Comitear.** El mensaje de commit y la descripción del PR explican el *por qué*, no solo el *qué* — el *qué* ya lo dice el diff.

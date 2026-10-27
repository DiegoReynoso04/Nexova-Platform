# Progress — Nexova Monorepo

Estado vivo del proyecto. Cada entrada nueva se añade **arriba**, con fecha, y se corrige (no solo se acumula) si contradice el estado actual del repo. Ver skill `.agents/skills/memory-bank-sync/SKILL.md`.

---

## 2026-10-27 — Auditoría de rendimiento: H1 (espacio reservado de la navegación)

**Estado: código hecho y comiteado; medición intermedia pendiente (la hace el usuario).** Rama `feature/perf-audit`. Sin push. **No se empieza H2 hasta que el usuario revise la medición de H1.**

- **Código (`uis/backoffice`):**
  - **`lib/auth-routes.ts`:** función pura `headerNavMode(pathname, status)` → `session` | `reserved` | `access` | `none`. Es `reserved` en `initializing`/`checking` solo si `routeAccess(...) === 'wait'`.
  - **`components/ui/nav-link.tsx`:** `NavLinkPlaceholders` (contexto). Dentro, cada `NavLink` se pinta como `<span>` con las mismas clases y el mismo texto, sin `href`.
  - **`components/auth/account-nav.tsx`:** la pieza `SessionLinks({ placeholder })` tiene la única lista de enlaces. La rama `reserved` es un `<div aria-hidden="true" inert className="invisible …">` con `SessionLinks placeholder`, un hueco `w-40` en el lugar del email y el mismo `Button` deshabilitado con `tabIndex={-1}`.
  - **Sin tocar:** el guard, `use-auth-session.ts` y la estrategia de sesión (D10, AUTH-02).
  - **Por qué un contexto y no una prop en cada `NavLink`:** el test del único enlace «Inventario» exige el literal `<NavLink href={INVENTORY_PRODUCTS_PATH} activePrefix={INVENTORY_PATH}>`, sin otros props.
- **Tests:**
  - Jest, en `__tests__/auth/auth-routes.test.ts`: los casos de `headerNavMode` (`auth-routes.ts` sigue al 100 %);
  - `tests/production-source.test.mjs`: una regla nueva, «la navegación reservada es invisible, inerte y sin enlaces». La hacen fallar 4 mutaciones: sin `placeholder`, sin `inert`, un `NavLink` en la rama y el `NavLink` sin `span`.
- **Validación:**
  - `tsc` y `lint` limpios;
  - `build` correcto;
  - Jest, 239/239;
  - `node:test`, 496/499.

  Los 3 fallos de `node:test` son de `tests/inventory-contract.test.mjs` (categorías, oficinas y tipos de salida) y **ocurren igual sin H1** (comprobado con `git stash`). La regex del test esperaba `\n` tras `class X(StrEnum):`, y en esta copia de trabajo `services/api/app/modules/inventory/vocabulary.py` tiene finales CRLF (`core.autocrlf=true`; el índice está en LF).

  **Corregido en un commit propio, aprobado por el usuario** (`test(backoffice): el contrato del inventario tolera finales de línea CRLF`): `\r?\n` en la regex de `backendEnum`. Solo cambia el test; no toca código de producción ni invalida el build de H1 del 3003.
  - el contrato pasa 7/7 con `vocabulary.py` en CRLF y en LF;
  - la mutación de control (`'hardware'` alterado en `types/inventory.ts`) hace fallar 1 test;
  - `node:test` completo vuelve a 499/499.
- **Medición intermedia:** pendiente. El usuario avisa cuando los 5 JSON estén en `audit/after/steps/H1/`. La comprobación de la vista Accessibility de DevTools también está pendiente: no se anota nada hasta que el usuario la confirme.
- **Verificación con el build de producción en el 3003** (variables desde PowerShell; desde Git Bash, MSYS convirtió `NEXT_PUBLIC_API_URL=/backend` en `C:/Program Files/Git/backend` dentro del bundle, así que el build se repitió desde PowerShell):
  - `curl.exe` sin token: el HTML de `/suppliers` ya trae la navegación reservada (6 `span`, el hueco y el botón deshabilitado), sin más `href` en la cabecera que el de la marca (`/`), que ya estaba. `/login` no cambia;
  - Network: con token, en `/suppliers`, ninguna precarga `_rsc` antes de `/backend/auth/me`; las de las rutas protegidas solo aparecen después, con los enlaces reales. Sin token, las únicas precargas son `/login`, `/register`, `/forgot-password` y `/`, esta última del enlace de la marca y anterior a H1;
  - foco: con el HTML del servidor sin scripts, el botón reservado no recibe el foco (`inert`) y el enlace de la marca sí. La vista Accessibility de DevTools no se pudo comprobar desde las herramientas del agente (su árbol no aplica `aria-hidden`, comprobado con un control); queda para el usuario;
  - altura de la cabecera reservada frente a la final: 134,4 frente a 134,4 px a 1024 px de ancho, y 170,4 frente a 170,4 px a 375 y 412 px;
  - AUTH-02: login incorrecto (aviso, sin token), login correcto, logout (token borrado, `/login`, cabecera pública de 52,8 px), sin token → `/login`, token manipulado → 401 en `/auth/me`, token borrado y `/login`;
  - a 375 px, sin scroll horizontal en las tres vistas;
  - para la verificación se creó una cuenta de prueba en la TinyDB de desarrollo, con credenciales generadas en el scratchpad de la sesión, fuera de la repo.

## 2026-10-27 — Auditoría de rendimiento: revisión de F2 y F3 (`AUDIT.md`)

**Estado: F3 hecha.** Rama `feature/perf-audit`. Sin push. Solo documentación: no se ha tocado código de las apps. **Siguiente: H1.**

- **Revisión de F2 (decisiones del usuario, ya en `audit/skills-findings.md` §3, §7 y §8):**
  - **§8.1:** H4 sigue como requerida, en último lugar. En `REPORT.md` se dirá que su impacto es en bytes, no en la puntuación.
  - **§8.2:** S2 sigue como sugerencia.
  - **§8.3, H1 aprobado con una condición:** la navegación reservada se pinta con `<span>`, con las mismas clases y el mismo texto, `invisible`, `aria-hidden` e `inert`, sin `Link` ni `href`. Así Next no precarga rutas protegidas y no hay enlaces protegidos en el HTML sin sesión. La pieza compartida de `account-nav.tsx` elige con una prop entre enlace y `span`; el test del único enlace «Inventario» debe seguir pasando. Se verifica en Network, con el build de producción: ninguna precarga de esas rutas antes de que `/auth/me` responda.
  - **H3:** el comando del CSS se documenta en un `uis/website/README.md` nuevo, que se crea en el commit de H3. Motivos: la regla pide un README por app y el sitio no lo tenía, y el paso de generación es solo de esta app. `uis/README.md` sigue como índice y se corrige su fila del sitio («Play CDN, no build step»).
  - **S1:** se aplica tras H3, en su propio commit, si sigue teniendo sentido.
  - **Orden final:** H1 → H2 → H3 → H4 → S1 → R1 → R2 → medición final.
  - **Mediciones:**
    - tras cada paso, 1 ejecución por caso afectado; solo el JSON, en `audit/after/steps/<paso>/`, sin capturas;
    - la medición final, completa (12 casos, 3 ejecuciones, capturas y JSON en `audit/after/<app>/<página>/`);
    - la fila `audit/` de `.agents/rules/monorepo-structure.md` lo recoge.
- **F3 — `AUDIT.md` (raíz, nuevo):**
  - **Contenido:**
    - §1, alcance y método, con por qué esas páginas (`/` y `/incidents` del backoffice no se miden), el criterio y las limitaciones;
    - §2, los 12 casos con enlace a cada captura;
    - §3, H1–H4 con su causa raíz (en H1, la cuenta de la geometría: la víctima es `main` y la causa es la cabecera) y, en breve, S1–S5, N1–N2 y X1–X4;
    - §4, la refactorización;
    - §5, el plan.
  - **Refactorización, verificada en el código:**
    - **R1 (`components/ui/table-scroll.tsx`):** 4 tablas con el mismo armazón y `px-3 py-2 font-semibold` repetido 25 veces. A `supplier-table.tsx` le falta `relative`, que la lista de excepciones del test (`production-source.test.mjs:413-418`) lleva como pendiente. Las 3 tablas de `/incidents` quedan fuera (otro estilo). Hay que ajustar el test de `:354`;
    - **R2 (`hooks/use-inventory-list.ts`):** `use-inventory-assets.ts` y `use-inventory-orders.ts`, de 159 líneas cada uno, solo difieren en nombres. Los envoltorios conservan su API: los 6 componentes de activos y el del historial no cambian;
    - **R3 (de F0, candidato, no se aplica):** la lista de errores por campo de los avisos se repite en `supplier-error.tsx:73-77`, `incident-error.tsx:78-84` y también en `auth-error.tsx:91-95`. Sería `components/ui/field-error-list.tsx`, genérico en el tipo de campo, con su `Record` de etiquetas. No se aplica porque no toca ninguna métrica y amplía el riesgo de AUTH-02. El R3 de F0 no constaba en la repo (era otra sesión); el usuario lo recuperó al revisar F3 y se añadió en un commit propio de documentación;
    - **R4 (candidato, no se aplica):** el bloque «Cargando…» es idéntico en 4 vistas. Se identificó en F3;
    - **R5 (descartado):** la cabecera (87 líneas) y el pie (25) se repiten en los 3 HTML del sitio. Solo se compartirían inyectándolos con JS (empeora el SEO y añade CLS) o con un build (reestructura).
- **Sin impacto técnico:** no cambia código de las apps; `techContext.md` no se toca.

## 2026-10-27 — Auditoría de rendimiento: F2 (skills)

**Estado: hecha y revisada por el usuario** (decisiones en la entrada de arriba). Instalación comiteada en `8871787` y hallazgos en `audit/skills-findings.md`. Rama `feature/perf-audit`. Sin push. La sesión de la instalación no detectaba skills nuevas en `.claude/skills/` (`Unknown skill: core-web-vitals`); los pasos 3–5 se hicieron tras reiniciarla.

- **D4, decidida tras F1:** la imagen sobredimensionada (`uis/website/src/img/ambiente-trabajo-nexova.jpg`) se corrige solo si la skill la señala como causa de una auditoría fallida (criterio de «requerida»). En ese caso, en una fase de corrección posterior, con `npx sharp-cli@<versión fija>` puntual y sin añadir dependencias.
- **Paso 1 — ensayo en el scratchpad, fuera del repo:**
  - **CLI:** `skills` 1.7.4 con `DISABLE_TELEMETRY=1`. El CLI lo respeta: `dist/cli.mjs` desactiva la telemetría con `DISABLE_TELEMETRY` o `DO_NOT_TRACK`.
  - **Flags reales:** existen `-a/--agent`, `--copy`, `-s/--skill`, `-y` y `-l/--list`.
  - **Qué crea:** con `-a claude-code --copy`, solo `.claude/skills/<skill>/` (`SKILL.md` y `references/`), sin enlaces simbólicos y sin `.agents/`, más un `skills-lock.json` en la raíz.
  - **Revisión del contenido:** 7 archivos Markdown, unos 48 KB. No hay scripts ni nada que se ejecute, y ninguna instrucción pide acciones fuera del análisis de rendimiento. Solo contienen enlaces a documentación y fragmentos de ejemplo (un service worker, `sendBeacon` para RUM, `PerformanceObserver`). RUM.md pide autorización antes de añadir telemetría.
  - **Conflicto con nuestras reglas:** MEASUREMENT.md propone el CLI de Lighthouse o PageSpeed como alternativa. Aquí no se usan.
  - **Origen:** `addyosmani/web-quality-skills` en `afa8da942115f2961fdbfa80807ea0b232ff6c00` (merge de la PR #19, «web-quality-skills-v2», 2026-08-24). Los 7 archivos son idénticos a los de ese commit en GitHub, salvo los finales de línea (CRLF en la copia).
- **Paso 2 — instalación en el repo:**
  - **Ubicación:** `.claude/skills/core-web-vitals/` y `.claude/skills/performance/`, como copias. `.agents/skills/` y los `package.json` siguen sin cambios (comprobado con md5), y `.gitignore` no excluye `.claude/`.
  - **`skills-lock.json` no se versiona:**
    - solo guarda el repositorio, la ruta y un `computedHash` del contenido, sin SHA ni ref, así que no documenta la versión;
    - restaurar con él (`experimental_install`) descargaría el `main` de ese momento;
    - además, sería un archivo nuevo en la raíz fuera de la convención de carpetas.

    La evidencia del origen es el SHA del cuerpo del commit, junto con los dos `computedHash`.
- **Paso 3 — ejecución de las skills:**
  - `core-web-vitals` y después `performance`, invocadas con la herramienta de skills, leyendo también `CLS.md` y `LCP.md`. `INP.md` no aplica: TBT máximo de 80 ms y ninguna interacción lenta;
  - evidencia: solo los 12 JSON de `audit/before/`, sin volver a medir y sin CLI de Lighthouse ni PageSpeed;
  - desviaciones del flujo de las skills, documentadas en `skills-findings.md` §1: sin CrUX (local) y sin traza nueva; las causas que no confirma el JSON van como «causa probable».
- **Paso 4 — `audit/skills-findings.md`** (nuevo):
  - **Requeridas:**
    - **H1**, la cabecera del backoffice crece al validarse la sesión. `AccountNav` devuelve `null` en `initializing`/`checking` y después pinta 8 elementos: 53 → 170 px en mobile (0,936 × 117/823 ≈ 0,133, la cifra medida) y 53 → 134 px en desktop (el 0,032). La corrección reserva la navegación invisible e inerte en las rutas protegidas; no toca el guard (D10);
    - **H2**, el resumen de `/incident-manager` pasa de una fila «Cargando resumen…» a 4 listas apiladas en mobile (0,2344). La corrección reserva las filas desde el vocabulario, porque `readCounts` garantiza una por valor;
    - **H3**, el Play CDN de Tailwind (D3);
    - **H4**, la foto (D4), como caso límite.
  - **Sugerencias:**
    - S1, `logo.svg` sin dimensiones o sin `fetchpriority`; se decide tras H3;
    - S2, el CSS bloqueante del login (caso límite: la skill exige un *render delay* largo y hay 71 ms; `inlineCss` es experimental);
    - S3, los polyfills: el chunk `0zutzion2550z.js` empieza con el `polyfill-module` de Next, no con código de la app. No es accionable;
    - S4, `validations.js` sin minificar;
    - S5, los desplazamientos residuales de los filtros.
  - **Documentados sin corrección:** N1, el *render delay* por el guard (D10), y N2, el hueco FCP→LCP del login, que es un artefacto de la simulación (observado FCP = LCP = 78 ms).
  - **Descartados:** X1–X4, los artefactos del servidor local.
  - **Orden propuesto (§7):** H1 → H2 → H3 → H4, con las URLs y los modos que se vuelven a medir tras cada uno. Tres decisiones abiertas para el usuario (§8).
- **Regla:** `.agents/rules/monorepo-structure.md` (fila `audit/`) admite ahora `skills-findings.md` en la raíz de `audit/`.
- **Sin impacto técnico:** no cambia código de las apps; `techContext.md` no se toca.

## 2026-10-27 — Auditoría de rendimiento de los dos frontends: F0–F1

**Estado: en curso** (F1 hecha), en `feature/perf-audit`, creada desde `main` en `6877599`. Brief literal en `docs/perf-audit-brief.md` (`fb3cb15`). Sin push.

- **F0 — análisis y decisiones del usuario:**
  - **Ubicación:** `AUDIT.md`, `REPORT.md` y `audit/` en la raíz. `audit/` queda como carpeta de evidencias en `.agents/rules/monorepo-structure.md`.
  - **Medición:** solo en local, sin Netlify ni URLs públicas, con el panel Lighthouse de Chrome DevTools, que ejecuta el usuario (nunca el CLI de Lighthouse).
  - **Correcciones y refactorizaciones aprobadas:**
    - **D3:** Tailwind precompilado con su CLI en lugar del Play CDN. El CLI escanea también `src/js/*.js`, la versión va fijada y el antes/después se compara en desktop y a 375 px.
    - **R1:** `components/ui/table-scroll.tsx`.
    - **R2:** un hook genérico de carga de listados bajo `use-inventory-assets` y `use-inventory-orders`.
  - **D10:** la cascada del guard de autenticación se documenta como causa, pero no se corrige.
  - **Pendiente de instalar:** las skills core-web-vitals y performance, en F2.
- **F1 — medición inicial**, registro completo en `audit/before/runs.md`:
  - **Entorno:**
    - el sitio con `node uis/serve-website.mjs` en el 3000;
    - el backoffice con `npm run build` + `npm run start -- -p 3003`; `API_INTERNAL_URL` y las `NEXT_PUBLIC_*` solo en la sesión de PowerShell;
    - el contenedor `ui` parado durante la medición;
    - commit medido `fb3cb15`.
  - **Herramientas:** Lighthouse 13.4.1 y Chrome 155; `@tailwindcss/browser@4` resuelve a la 4.3.3.
  - **Alcance:** 12 casos en `audit/before/<app>/<página>/<página>-<modo>.{png,json}`. Son los 8 previstos más el login en frío y suppliers e inventory/products en mobile. `audit/after/` mantiene la misma estructura.
  - **Comprobado en los 12 JSON:**
    - `finalDisplayedUrl` es la URL pedida, sin redirección a `/login`;
    - el `formFactor` es el esperado;
    - el `benchmarkIndex` va de 3569,5 a 3892,5;
    - la Performance no varía más de 1 punto entre ejecuciones.
  - **Discrepancia sin efecto:** el JSON de suppliers desktop es de las 23:52:20 y no de la ejecución anotada a las 23:51:14; sus cifras son idénticas.
  - **Fuera de umbral:**
    - incident-manager mobile: Perf 82 y CLS 0,373;
    - suppliers mobile: CLS 0,136;
    - inventory/products mobile: CLS 0,135.

    El sitio no incumple ningún umbral (LCP mobile máximo 2,1 s). La parte del criterio que depende de la skill queda para F2–F3.
  - **Material para F3** («Observado, sin causa raíz todavía»):
    - el script del CDN bloquea el render (hasta 1150 ms estimados en mobile);
    - la foto de 1920×1156 se muestra a 576×347;
    - en index desktop, el LCP es `logo.svg`, sin `width`/`height`;
    - en mobile, las tres vistas del backoffice repiten el mismo desplazamiento de `main` (0,1337);
    - en incident-manager, la sección del listado añade 0,234 más;
    - en desktop, 0,032, con `main` en incident-manager y el header en las otras dos vistas;
    - en el login mobile, el hueco FCP→LCP de 900 ms solo aparece en la simulación.
  - **Artefactos del servidor local**, documentados y no corregidos: compresión, `no-store`, HTTP/1.1 y TTFB.
  - **Cierre:**
    - servidores parados;
    - `uis/backoffice/.next` reconstruido sin variables (rewrites vacíos en el `routes-manifest`);
    - `docker compose start ui` (website 200; `/backend/health` OK).
  - **Siguiente:** F2 (skills), F3 (`AUDIT.md`) y después una corrección por commit, volviendo a medir la misma URL.
- **Memory-bank:** se corrige la entrada de #infra-40, que seguía como «pendiente de PR».

## 2026-10-22 — #infra-40 (Docker para desarrollo; el despliegue en el VPS quedó fuera): F0–F7

**Estado: integrado en `main` con la PR #24 (merge `6877599`, 2026-10-25).** Historial: F0 y F1 en `6a49d6f`, F2 en `daede5e`, F3 en `0883f3d`, F4 en `cbeac39`, el tracker en `fe56224`, F5 en `f498ef5` y F7 en el commit `docs(infra-40)`; sin F6; sin push de F7), en `feature/docker-dev-env`, creada desde `origin/main` y actualizada con fast-forward a `db76772` (merge de la PR #23, el memory-bank del inventario). Al traer ese merge, `git stash pop` dio conflicto en esta entrada; se resolvió dejándola encima de la del 2026-10-21 (después, el stash ya aplicado se borró con `git stash drop`).

- **F0 — análisis, aprobado por el usuario con cambios:**
  - brief literal en `docs/infra-40-brief.md`, con una nota de equivalencias (`uis/website` es HTML estático, no Next.js; `/services` es `services/api`);
  - comprobado: Docker 29.7.2 y Compose v5.5.0 (`additional_contexts` desde 2.17); `node:24-alpine` y `python:3.14-slim` existen (amd64 y arm64); las 28 dependencias de `uv.lock` sin el grupo dev se resuelven solo con wheels para Linux x86_64 y CPython 3.14 (también `psycopg2-binary` 2.9.13); en Next 16.3 los rewrites de `next.config` se cargan al arrancar `next dev` y, con `next start`, salen del `routes-manifest.json` de `next build`; recarga en Docker con `watchOptions.pollIntervalMs` (Turbopack) y `WATCHPACK_POLLING` (vigilante de Next);
  - decisiones del usuario: D1 con un script `http` de Node para el website (la `busybox` de Alpine se compila sin `httpd`), D2 sin tocar CORS (`localhost:3001` sigue para el tracker fuera de Docker), D3 con build args en producción, D4–D7 como las propuso, y las fases F1–F7 del plan;
  - pendiente: el motor de Docker Desktop no arranca en la máquina del usuario (el backend falla al crear `sailor-ingest.sock`), que lo arregla él; sin motor no se ha ejecutado `busybox --list` ni verificado el polling.
- **F1 — base:**
  - **Fin de línea:** el índice está entero en LF (449 `i/lf`, 22 `i/none`, 2 `i/-text`, 0 CRLF); el CRLF solo está en la copia de trabajo (258 `w/crlf`) por `core.autocrlf=true`. `.gitattributes` nuevo, solo con `*.sh text eol=lf` y `Dockerfile text eol=lf`; no hacía falta renormalizar (no existía ninguno). `.dockerignore` no entra: Docker quita el `\r` de cada patrón (`TrimSpace` en `moby/patternmatcher`). El `.env` con CRLF queda por verificar en F4.
  - **`.env.example` en la raíz** (sin secretos): las 12 variables que lee la API, agrupadas como en `services/api/.env.example`, más `API_INTERNAL_URL=http://api:8000` (variable solo de servidor para el rewrite; sin `NEXT_PUBLIC_` para no incorporarse al JavaScript del navegador), `NEXT_PUBLIC_API_URL=/backend`, `NEXT_PUBLIC_INVENTORY_API_URL=/backend` y, comentada como el resto del trío de Resend, `PASSWORD_RESET_URL=http://localhost:3001/reset-password`. El aviso sobre los valores con `$` queda pendiente de verificar en F4. Comprobado: `.env` de la raíz ignorado (`.gitignore:6`), `.env.example` no (`.gitignore:11`), y ningún `.env` en el historial (`git log --all -- .env '**/.env'`: 0 commits).
  - **`services/api/requirements.txt`:** `uv export --frozen --no-dev --no-emit-project --format requirements-txt -o requirements.txt` desde `services/api` (la cabecera de `uv` recoge el comando); 28 paquetes con hashes; sin `nexova-incident-analyzer` ni `nexova-shared` (no están en `uv.lock`). `uv.lock` y `pyproject.toml` sin cambios.
  - **Corrección tras la revisión del usuario:** `PASSWORD_RESET_URL` estaba activa y `RESEND_API_KEY` y `EMAIL_FROM` comentadas; `config.py` exige las tres juntas o ninguna (`ConfigError`), así que con solo `JWT_SECRET_KEY` y `DATABASE_URL` la API no habría arrancado. Ahora va comentada, con el mismo valor. Comprobado cargando las variables activas del archivo en `Settings.from_env` (con valores ficticios en las dos obligatorias) más `require_auth()` y `require_database()`: sin error.
  - **Para F2:** `requirements.txt` lleva hashes, así que `uv pip install -r` exige hash en cada requisito; los dos paquetes locales (`packages/shared` y `packages/incident-analyzer`) se instalan en un comando aparte, sin dependencias.
  - **Para F4:** comprobar que, con el bind mount, las `NEXT_PUBLIC_*` del entorno de Compose ganan al `uis/backoffice/.env.local` del host; si ganara `.env.local`, el navegador iría a `localhost:8000`.
  - **Para F5:** comprobar que `requirements.txt` sigue a `uv.lock` exportando al scratchpad y comparando con `diff`.
- **F2 — imagen de la API (2026-10-23), con Docker Desktop ya en marcha:**
  - **D1 confirmado:** `docker run --rm node:24-alpine busybox --list` sale con 0 (304 applets) y `grep httpd` con 1 (Alpine 3.24.1, Node v24.20.0).
  - **`services/Dockerfile`:** `python:3.14.6-slim` (Debian 13, glibc 2.41; la misma versión del venv); `uv` 0.12.21 con `COPY --from=ghcr.io/astral-sh/uv:0.12.21` (la versión que generó `requirements.txt`; binario estático, sin pip ni red en esa capa); `uv pip install --system --no-cache --require-hashes -r requirements.txt`; los paquetes del monorepo por **`PYTHONPATH`** (`/packages/shared:/packages/incident-analyzer`), sin instalarlos, porque instalarlos pediría `setuptools` a PyPI (la imagen no lo trae) y en F4 una copia instalada taparía el bind mount de `packages/` (precedente: `pythonpath` de pytest en `pyproject.toml`); capas en orden de caché (dependencias, paquetes, código); `CMD` uvicorn con `--factory`, `--host 0.0.0.0`, `--port 8000`, `--workers 1` y `--reload`; `EXPOSE 8000`; sin ENV ni ARG con secretos.
  - **El `.dockerignore` del contexto principal no se aplica al contexto adicional `packages`:** la primera imagen llevaba `__pycache__` y `.pyc` del host (también de CPython 3.10). Se corrige con una etapa `monorepo-packages` que copia los dos paquetes y borra la caché de bytecode; la imagen final solo copia el resultado.
  - **`services/.dockerignore`:** lo del brief con `**/` (`__pycache__`, `*.pyc`, `.env*`, `tests`, `*.log`) más `api/.venv`, `api/data`, `.coverage*`, `.pytest_cache`, `htmlcov` y `*.egg-info`.
  - **Verificado:** build correcto (28 paquetes con hashes); en `/app` y `/packages` no hay `.env*`, `tests`, `.venv`, `data`, `*.egg-info` ni `__pycache__`, y en toda la imagen ningún `.env*` ni `*.egg-info`; `nexova_shared`, `incident_analyzer` y `app.main` importables; `docker history --no-trunc` sin `secret`, `password`, `DATABASE_URL` ni `JWT`; con `--env-file .env`: `/health` 200, `/docs` 200, y los logs sin la URL, el usuario, la contraseña ni el host de la base, sin `JWT_SECRET_KEY` ni `RESEND_API_KEY`. Imagen de 337 MB.
  - **Sin `.env`:** el `ConfigError` de `JWT_SECRET_KEY`, sin secretos en el traceback. **Con `--reload` el contenedor no termina:** el reloader (PID 1) sigue vivo esperando cambios y el contenedor queda en `running` con la API caída. Sin `--reload` sale con código 1.
  - **Para F4:** un `healthcheck` sobre `/health` para que un arranque fallido se vea (`unhealthy`) aunque el reloader siga vivo; `--reload-dir /packages` además de `/app/api`, porque uvicorn solo vigila el directorio de trabajo. Ojo: `--reload-dir` **sustituye** al directorio vigilado por defecto, así que hay que pasar los dos (`--reload-dir /app/api --reload-dir /packages`) y comprobarlo en la línea «Will watch for changes in these directories» del log.
- **F3 — imagen de interfaces (2026-10-23):**
  - **`uis/Dockerfile`:** `node:24.20.0-alpine` fijada; `npm ci` del backoffice desde su `package-lock.json` (con las dependencias de desarrollo, que `next dev` necesita); `uis/website` no tiene `package.json` y no instala nada (lo dice un comentario); copia las dos apps, `serve-website.mjs` y `start.sh`; `CMD ["sh", "./start.sh"]`; `EXPOSE 3000 3001`; solo `NEXT_TELEMETRY_DISABLED` como ENV. El lockfile ya traía las variantes musl de `@next/swc`, `lightningcss` y `@tailwindcss/oxide`: `npm ci` las instala sin tocarlo (md5 igual) y cargan de verdad (`@next/swc` nativo, no WASM). npm 11 no ejecuta los scripts de instalación de `@parcel/watcher` y `unrs-resolver` (no están en `allowScripts`); no hacen falta, porque sus binarios musl vienen precompilados.
  - **`uis/serve-website.mjs`:** solo `http`, `fs` y `path`; `/` → `index.html`; archivos tal cual con su `content-type`; inexistente → `404.html` con 404; rechaza `..`, `%2e%2e`, `%5c` y `%00` (siete intentos, todos 404); solo GET y HEAD (405 con `Allow`); lee el archivo en cada petición.
  - **`uis/start.sh`:** en BusyBox 1.37, **`wait -n` espera a todos y devuelve 0**, así que se vigila con `kill -0`. **Primer intento con un fallo:** al matar `next dev` con KILL, su `next-server` quedaba huérfano (hijo del PID 1) y el contenedor seguía `running`. Se corrige arrancando cada app en su propio grupo con `setsid` y enviando las señales al grupo, con KILL a los 10 s si algo no termina.
  - **`uis/.dockerignore`:** `**/node_modules`, `**/.next`, `**/.env*`, `**/*.log`, `talent-pipeline-tracker`, `**/coverage` y `**/*.tsbuildinfo` (contexto de 1,57 MB).
  - **`uis/backoffice/next.config.ts`:** `rewrites()` de `/backend/:path*` a `API_INTERNAL_URL` (sin barra final) solo si está definida; si no, `[]`. Polling activado por `WATCHPACK_POLLING`, la variable que ya lee el vigilante propio de Next, reflejada en `watchOptions.pollIntervalMs` para Turbopack (un solo interruptor para los dos vigilantes); sin ella, no hay `watchOptions`.
  - **Verificado:** build en 16 s con 591 paquetes; imagen de 884 MB sin `.env*`, `.next`, `coverage`, `talent-pipeline-tracker` ni binarios glibc o de Windows; `docker history` sin secretos. En una red temporal (`nexova-f3`, sin Compose): website 200/404 como se espera; backoffice `/login` 200; `/backend/health` 200 `{"status":"ok"}`, con la query string conservada y el 401 de la API intacto; `wget http://api:8000/health` desde la ui, y `api` resuelto por la DNS de Docker. `docker stop` en 1,2 s (código 0); TERM a `next dev`: sale con 1 en 2 s; KILL a `next dev` o al website: sale con 137 en 1–2 s. Contenedores y red de prueba borrados (las imágenes se quedan).
  - **Validación del backoffice en el host** sin `API_INTERNAL_URL`: `tsc` y `lint` sin errores, `build` correcto (rewrites vacíos en el `routes-manifest`), `node:test` 491/491 y Jest 222/222. Con `API_INTERNAL_URL=http://api:8000`, el build sale con 0 y el manifest lleva el rewrite; después se reconstruyó el `.next` del host sin la variable. El aviso de Turbopack «multiple lockfiles» es anterior: lo provoca el `package-lock.json` de la raíz (Hito 2).
  - **Para F4:** el contenedor `ui` no debe recibir el `.env` entero (en la prueba de F3 lo recibió, con los secretos de la API): solo `API_INTERNAL_URL`, las `NEXT_PUBLIC_*` y `WATCHPACK_POLLING`.
- **F4 — `docker-compose.yml` (2026-10-24):**
  - **Decisiones del usuario (2026-10-24):** Docker es el **único** modo de arrancar la plataforma en desarrollo: un solo `.env` (el de la raíz) y un solo juego de puertos (3000 website, 3001 backoffice, 8000 API). `services/api/.env` y `uis/backoffice/.env.local` dejan de usarse para arrancar; son del usuario y no se borran ni se editan. `services/api/data` del host se monta en la API (en producción, un volumen con nombre). El tracker queda fuera de Docker y pasará al 3002, pendiente del ok del usuario a la lista de cambios.
  - **Servicios:**
    - `api`: contexto `./services` con `additional_contexts: packages`; bind mounts de `app/` y de los dos paquetes; `data/` del host; `--reload-dir /app/api --reload-dir /packages`, confirmado en el log («Will watch for changes in these directories: ['/app/api', '/packages']»); healthcheck con `urllib` a `localhost:8000/health` dentro de su contenedor (la imagen no trae curl ni wget); puerto 8000.
    - `ui`: contexto `./uis`; bind mounts de `website/` y `backoffice/`; `node_modules` y `.next` en volúmenes anónimos; puertos 3000 y 3001; `depends_on: api: service_healthy`.
    - Red `nexova-net` y proyecto `name: nexova`.
  - **Variables:** `api` con `env_file: .env` obligatorio. `ui` solo con `API_INTERNAL_URL`, `NEXT_PUBLIC_API_URL`, `NEXT_PUBLIC_INVENTORY_API_URL` y `WATCHPACK_POLLING`, interpoladas con `${VAR:?…}`. **Efecto:** sin `WATCHPACK_POLLING` en el `.env` falla cualquier comando `docker compose` (también `exec` y `ps`). El usuario añadió `WATCHPACK_POLLING=true` a su `.env` (presente; también está en `.env.example`).
  - **Incidencia:** el primer `up` dejó la API `unhealthy` (y la ui sin arrancar, por el `depends_on`) porque el `.env` de la raíz se había vuelto a copiar desde `.env.example` (idéntico, sin secretos). El usuario lo restauró; los tres `$` que contiene están en comentarios.
  - **Verificado:**
    - `config --quiet` sale con 0 y `up --build -d` también, con la API `healthy`;
    - los dos contenedores están en `nexova-net`;
    - por nombre de servicio: `wget http://api:8000/health` desde la ui y `localhost:3001/backend/health` (en el log de la API, origen 172.19.0.3, la ui);
    - en la ui solo están `API_INTERNAL_URL` y las `NEXT_PUBLIC_*`, sin ningún secreto ni otra variable de la API;
    - la API ve los 8 usuarios del `auth.json` del host, y los JSON de `data/` no han cambiado durante las pruebas (SHA-256 iguales).
  - **f) `.env.local` del host:** está montado en el contenedor y Next lo carga (`Environments: .env.local`), pero el JavaScript que se sirve al navegador lleva `"/backend"` y ninguna `localhost:8000` (la única aparición es un comentario de `lib/inventory-api-client.ts`). Gana el entorno de Compose, como documenta `environment-variables.md` («Environment Variable Load Order»: `process.env` antes que `.env.local`). Riesgo: una variable que Compose no defina sí se tomaría de ese `.env.local`.
  - **g) Recarga en caliente:**
    - website en 0,2 s (lee cada archivo en cada petición);
    - API (`app/main.py`) en 1,1 s y `packages/shared` en ~1 s (`StatReload`, que ya sondea);
    - **backoffice: no recarga con Turbopack** (el bundler por defecto de `next dev`), ni sin polling ni con `watchOptions.pollIntervalMs`, ni siquiera con un cambio hecho dentro del contenedor. En el host, sin Docker, sí (~2 s). En un contenedor de prueba, **`next dev --webpack` con `WATCHPACK_POLLING=true` recarga en ~2 s**, y sin polling no.
    - **Decisión del usuario (2026-10-24):** `next dev --webpack` en `uis/start.sh`, y se quita `watchOptions` de `next.config.ts`, porque Watchpack lee `WATCHPACK_POLLING` por su cuenta. Comentarios de `start.sh`, `next.config.ts` y `docker-compose.yml` actualizados con lo comprobado. Con la ui reconstruida (`▲ Next.js 16.3.2 (webpack)`), el backoffice recarga en 2,4 s (0,5 s en una segunda pasada) y el website sigue al instante. Validación de `uis/backoffice` en el host tras el cambio de `next.config.ts`: `tsc` y `lint` sin errores, `build` correcto (rewrites vacíos sin `API_INTERNAL_URL`), `node:test` 491/491 y Jest 222/222.
    - Los archivos de prueba se restauraron byte a byte (`git diff` vacío).
  - **h) Desde cero:** `down --rmi local --volumes` y `up -d` sin `--build` salen con 0, y la plataforma responde a los 17 s gracias a la caché de BuildKit. Con `build --no-cache`: 31 s de build y 46 s hasta responder, sin contar la descarga de las imágenes base.
  - **i) Auditoría:** en `docker-compose.yml` y los dos Dockerfile, el `grep` de `secret|password|key|postgresql://|eyJ` solo encuentra comentarios, y ningún valor del `.env`; `.env` ignorado y sin commits.
  - **Tests y `.env`:** ningún test de los subproyectos lee `services/api/.env` ni `uis/backoffice/.env.local`. node:test y Jest solo tocan `process.env` dentro del test y lo restauran; la API no carga `.env` (`config.py:3-4`).
  - **Comandos dentro de la API** (la imagen no instala el proyecto: no existen `seed`, `create-admin` ni `seed-inventory`):
    - `docker compose exec api python -m app.seed`
    - `docker compose exec api python -m app.auth.create_admin --email … --name …`
    - `docker compose exec api python -m app.modules.inventory.seed --email …`
    - `docker compose run --rm -v ./scripts:/app/scripts:ro -v ./data/raw:/app/data/raw:ro -e PYTHONPATH=/app/api:/packages/shared:/packages/incident-analyzer api python /app/scripts/seed_incidents.py`
    - Comprobados solo con `--help`; `app.seed`, que no usa argparse, solo importándolo.
  - **Para F7:** la documentación (`docs/local-development.md`, los README, `AGENTS.md` §4 y `uis/backoffice/CLAUDE.md`) debe presentar Docker como el único modo de arranque, con los comandos de arriba.
- **Tracker al puerto 3002 (2026-10-24, commit aparte de F4, aprobado por el usuario):** el 3001 es del backoffice en Docker y el tracker queda fuera de Docker.
  - Cambiado: `uis/talent-pipeline-tracker/package.json` (`dev` y `start`), su README y su `SPECS.md` (con nota del cambio), `uis/README.md` y `README.es.md`, el texto de un test (`tests/auth.test.mjs`); `CORS_ALLOWED_ORIGINS` = solo `http://localhost:3002` en el `.env.example` de la raíz (el website no llama a la API y el backoffice va por su mismo origen) y `http://localhost:3000,http://localhost:3002` en `services/api/.env.example` y su README; `docs/local-development.md`, `docs/auth-password-reset.md` y `memory-bank/techContext.md`; en `docs/auth-frontend.md` se conservan P-1 y P-5 con una nota.
  - Validación del tracker: `tsc` sin errores; `lint` con los 4 errores conocidos (`react-hooks/set-state-in-effect` en `use-notes`, `use-record-detail` y `use-records`); `node:test` 55/55. No se arrancó.
  - **Resuelto en F7** (se escaparon de la lista; el usuario las pasó a F7): menciones del tracker en el 3001 en `AGENTS.md:51`, `memory-bank/techContext.md:36`, `:177` y `:188`, `uis/backoffice/README.md:103` y `docs/auth-password-reset.md:265`.
- **Prueba del usuario en el navegador, con la plataforma en Docker (2026-10-24), todo correcto:** login con `Authorization` por `/backend`, inventario, `/incidents` con subida y exportación, `/suppliers`, `/incident-manager`, recuperación de contraseña con el enlace al 3001, ninguna petición a `:8000` y recarga del backoffice. El error de hidratación de la consola lo provoca una extensión de su navegador (atributos `bis_*`), no el código.
- **Un solo `.env` (2026-10-25):** el usuario borró `services/api/.env` y `uis/backoffice/.env.local`. Comprobado con `ls`: ya no existen (solo quedan los `.env.example`), y la plataforma sigue respondiendo; el login, según el usuario, también.
- **Decisión del usuario (2026-10-25): el despliegue en el VPS queda fuera de esta entrega. No hay F6.**
- **F5 — tests (2026-10-25):**
  - `uis/backoffice/tests/next-config.test.mjs` (node:test, 6 tests): sin `API_INTERNAL_URL` (o con una cadena vacía o espacios) `rewrites()` devuelve `[]`; con `http://api:8000`, `/backend/:path*` → `http://api:8000/:path*`; las barras finales y los espacios se normalizan; la config no tiene `watchOptions` (a petición del usuario, sin exigir que `rewrites` sea la única clave, para no romper con opciones futuras ajenas a Docker); `process.env` queda como estaba. Cada caso importa el módulo con una query distinta y restaura la variable en un `finally`. Primer intento con un error de lint en el propio test (`@next/next/no-assign-module-variable` por una variable llamada `module`), corregido.
  - `services/api/tests/test_requirements_lock.py` (unittest, 6 tests, con `tomllib`, sin llamar a uv): cada paquete de `requirements.txt` tiene la misma versión en `uv.lock`; cada dependencia de `[project.dependencies]` está fijada; no aparecen `nexova-incident-analyzer` ni `nexova-shared`, ni el grupo dev; cada requisito lleva hashes en su línea lógica (con las continuaciones `\` unidas) y no hay hashes huérfanos. El mensaje de fallo dice cómo regenerarlo.
  - **Mutaciones (9, todas detectadas y deshechas, md5 iguales):** sin quitar la barra final; sin recortar espacios; `watchOptions` de vuelta; destino sin `:path*`; otra versión de fastapi; falta una dependencia del proyecto; `pytest` en `requirements.txt`; `nexova-shared` en `requirements.txt`; un requisito sin hashes. **La última sobrevivió al primer intento** (el test partía el archivo por líneas que empiezan por letra y seguía viendo los hashes de debajo); se corrigió para leer líneas lógicas.
  - **`uis/serve-website.mjs`** (aprobado por el usuario): exporta `resolveRequestPath` y solo escucha si es el programa principal (`node serve-website.mjs` desde `start.sh`). Test en `uis/tests/serve-website.test.mjs` (node:test, 8 tests; comando `node --test "uis/tests/*.test.mjs"` desde la raíz): `/`, archivos con extensión, query y fragmento ignorados; las siete variantes de `..` de F3, `..` aunque quede dentro (`/src/../index.html`, porque la comprobación final `startsWith(ROOT)` tapaba la mutación), barra invertida, byte nulo y decodificación inválida → `null`. Mutaciones detectadas: aceptar `..`, aceptar `\` y aceptar `%00`. Con la ui reconstruida (Compose no monta ese archivo): `/` 200 con el index, `/no-existe` 404 con `404.html`, y las siete variantes de `..` dan 404.
  - **Validación** (antes → después): `uis/backoffice` `tsc` y `lint` sin errores, `build` correcto, `node:test` 491 → 497, Jest 222 (sin cambios); `uis/` (nuevo) 8 tests; `services/api` `unittest` 409 → 415 y pytest (`uv run --no-sync python -m pytest`) 612 → 618, con 3164 subtests.
- **F7 — documentación (2026-10-25), solo documentación, sin tocar código:**
  - Docker como único modo de arranque en `docs/local-development.md` (reescrito), `AGENTS.md` §4 (filas de `uis/` y Docker, bloque «Docker (ticket #infra-40)» y un solo comando oficial de pytest, `uv run --no-sync python -m pytest`, con el porqué), `uis/backoffice/CLAUDE.md` (sección «Docker»: rewrite, `API_INTERNAL_URL`, `--webpack`, `WATCHPACK_POLLING`), `uis/backoffice/README.md`, `uis/README(.es).md`, `services/README(.es).md` y `services/api/README.md` (sección «Docker» con cómo regenerar `requirements.txt` desde `services/api` y por qué no aparecen los paquetes del monorepo; seeds y `create-admin` con `docker compose exec`). Las 6 menciones del tracker en el 3001 pasan al 3002. El `README.md` raíz no se toca.
  - `docs/infra-40-review.md` nuevo: qué se construyó, arranque, totales, trazabilidad de los criterios, decisiones y lo no verificado.
  - `techContext.md`: fila «Entorno de desarrollo (Docker)», sección «Docker (#infra-40)» y las líneas del tracker, `/backend`, pytest y el `.env` de la raíz. `projectbrief.md` sin cambios: ticket técnico, sin capacidad de negocio ni interlocutor nuevos.
  - **Decisiones del usuario tras el primer commit de F7 (2026-10-25), en un segundo commit:**
    - **`/incidents` y el rewrite:** se acepta como excepción documentada, pendiente de revisión del tech lead. Verificado antes de escribirla: `POST localhost:3001/backend/api/incidents/analyze` con `incidents-acceptance-synthetic.csv` (100 `customer_email` distintos) y un token firmado en local dentro del contenedor `api` (nunca impreso) → 200, y la exportación → 200. Después, con recuentos y sin mostrar valores: 0 emails en `docker compose logs ui` y en los de `api`; ningún archivo del contenedor `ui` tocado en esos minutos (`find -mmin -15`: solo el temporal de la propia comprobación); 0 archivos con algún email en todo el contenedor, montajes incluidos. **Dos falsos negativos evitados:** la `find` de BusyBox no tiene `-newermt` y su `grep` no tiene `--exclude-dir` (los dos fallaban en silencio con `2>/dev/null`); se rehízo con `-mmin` y la lista explícita de carpetas, con un control positivo (`NEXT_PUBLIC_API_URL`, 17 archivos). Regla reescrita en `uis/backoffice/CLAUDE.md` (sin Server Actions ni Route Handlers; único proxy, el rewrite), decisión en `docs/infra-40-review.md` y `techContext.md`.
    - **Regla nueva** en `uis/backoffice/tests/production-source.test.mjs` («sin Route Handlers ni Server Actions»; no existía): falla con un `route.*` en `app/` o un `'use server'` en el código de producción. Las dos mutaciones (un `app/zz-probe/route.ts` y un `actions.ts` con `'use server'`) la hacen fallar; deshechas.
    - **`.env.example`:** `uis/backoffice/.env.example` borrado (con la excepción `!.env.example` de su `.gitignore` y las referencias de su README); `services/api/.env.example` se queda con una cabecera que dice que no se usa para arrancar y remite al de la raíz.
    - **Guías antiguas** (`docs/auth-api.md`, `docs/auth-frontend.md`, `docs/centralized-incident-manager-review.md`, `docs/inventory-review.md` y `docs/inventory-frontend-review.md`): sin reescribir, con una línea al principio que remite a `docs/local-development.md`. Sus comandos `Copy-Item .env.example .env.local` del backoffice quedan como los de su fecha.
  - **Verificación final** (con la plataforma en Docker: `nexova-api-1` healthy, website 200, backoffice `/login` 200, `/backend/health` 200):

    | Subproyecto | Resultado |
    |---|---|
    | `uis/backoffice` | `tsc` y `lint` sin errores, `build` correcto, `node:test` 497/497 (498/498 tras la regla nueva del segundo commit), Jest 222/222 |
    | `uis/` | `node:test` 8/8 |
    | `uis/talent-pipeline-tracker` | `tsc` sin errores, `lint` con los 4 errores conocidos, `node:test` 55/55 |
    | `services/api` | `unittest` 415 OK; pytest 618 passed (3164 subtests) |

    `docker compose config --quiet` sale con 0; 196 enlaces relativos de los documentos tocados sin problemas; sin secretos ni archivos prohibidos en los commits de la rama.
- Impacto técnico: `.gitattributes`, `.env.example`, `requirements.txt`, `services/Dockerfile` y `services/.dockerignore`, `uis/Dockerfile`, `uis/.dockerignore`, `uis/start.sh` y `uis/serve-website.mjs` nuevos; `docker-compose.yml` nuevo; `uis/backoffice/next.config.ts` con el rewrite; `techContext.md` actualizado en F7.
---

## 2026-10-21 — Memory-bank: estado del frontend del inventario

**Estado: hecho.** Sin impacto técnico: solo `memory-bank/`, para reflejar el merge de la PR #22.

- **Verificado** (`git fetch origin`): `origin/main` en `410da71`, el merge de la PR #22 (`feature/inventory-frontend`, 2026-10-21, padres `8e5448e` y `0199caf`); `0199caf` está en `origin/main`.
- **Corregido:**
  - `techContext.md`: la fila «Inventario de equipos y materiales (UI)» (ya no «F6 pendiente de commit; sin PR todavía», sino F6 en `09e53ef`, limpieza en `0199caf` y merge `410da71`); la sección «Inventario: frontend del backoffice» (añade F6 y el merge); «Estado real en `main`» (cabecera verificada el 2026-10-21 en `410da71` y una línea de actualización con lo que integra la PR #22).
  - `projectbrief.md`: la fila del inventario, de «sin PR todavía» a integrada con la PR #22 (sin cambiar datos de negocio).
  - `progress.md`: la entrada de F6 (la subida y la PR estaban en futuro) y la de F1 («sin comitear»), corregidas en sitio; punto «Inventario (Hito 5)» en «Próximos pasos conocidos»; y, en esa misma sección, la línea de `uis/backoffice` («tiene `/incidents` y `/suppliers`»), que ahora lista las piezas de «Alcance actual» de su `CLAUDE.md`: `/`, `/incidents`, `/suppliers`, `/incident-manager` (PR #17), `/inventory/*` (PR #22) y la autenticación (AUTH-02/AUTH-03).

---

## 2026-10-21 — Frontend del inventario, F6: documentación y verificación final

**Estado: hecho.** Documentación comiteada en `09e53ef`, sobre F5 (`0fa0da3`), en `feature/inventory-frontend`. Después, con la confirmación del usuario, se restauró la demo y se borró la cuenta de prueba (ver «Limpieza» abajo). ~~La rama se sube y se abre la PR contra `main`.~~ *Corregido el 2026-10-21: la rama se subió y se integró en `main` con la PR #22 (merge `410da71`, 2026-10-21), con F1–F6 y la limpieza (`0199caf`).*

- **Documentación:**
  - `docs/inventory-frontend-review.md` (nuevo), con el estilo de `docs/inventory-review.md`: qué se construyó, arranque en PowerShell (API, `.env.local` con las dos variables, reinicio de `npm run dev`), suites y totales, recorrido manual de las 4 páginas, trazabilidad «Qué vamos a evaluar» → implementación → test → navegador, decisiones D1–D10 con sus ajustes y lo que no está verificado;
  - `uis/backoffice/README.md`: sección `/inventory/*`, `NEXT_PUBLIC_INVENTORY_API_URL`, estructura, validación y enlace a la guía;
  - `uis/backoffice/CLAUDE.md`: versión final de la sección «Inventario» (selector compartido, `ReadOnlyField`, `formInitialAssetId`, orden de los campos de la salida, stock reactivo, historial, arquitectura por página, `next typegen` y tests);
  - `AGENTS.md` §4: bloque «Inventario — frontend»;
  - `memory-bank/techContext.md`: la fila de la UI del inventario pasa a hecha, sección «Inventario: frontend del backoffice» con las decisiones permanentes y la nota de la demo corregida (ya no está en el neto del seed); `memory-bank/projectbrief.md`: el inventario con su interfaz.
- **Base de comparación:** `origin/main` en `8e5448e` (no hay rama `main` local). Commits de la rama: `0e0f133` (F1), `2dccef0` (`style(api)`), `72bd839` (F2), `064a569` (F3), `a591686` (F4) y `0fa0da3` (F5).
- **Verificación final (2026-10-21):**

  | Comprobación | Resultado |
  |---|---|
  | `uis/backoffice`: `tsc` / `lint` | sin errores |
  | `uis/backoffice`: `build` | correcto: `○ /inventory`, `○ /inventory/products`, `○ /inventory/orders`, `ƒ /inventory/orders/inbound`, `ƒ /inventory/orders/outbound` |
  | `uis/backoffice`: `node:test` | 491/491 (344 antes del frontend del inventario) |
  | `uis/backoffice`: Jest | 222/222, 13 suites (161 antes) |
  | `services/api`: `unittest` | 409 OK |
  | `services/api`: `pytest` | 612 passed, 3023 subtests; 1 aviso de dependencias (Starlette: `httpx` con `TestClient`), ajeno a la rama |
  | `git diff origin/main..HEAD --stat` | 60 archivos, +5172 / −19; idéntico con y sin `--ignore-cr-at-eol` |
  | Secretos (`git log -p origin/main..HEAD` y `git diff origin/main` con la guía nueva) | no encontrados: project-ref, usuario, contraseña, host del pooler, `DATABASE_URL`, `JWT_SECRET_KEY`, `*.pooler.supabase.com`, `postgresql://` con credenciales (0) y tokens `eyJ…` |
  | Archivos prohibidos en los commits de la rama | ninguno (`.env`, `.env.local`, `.vscode/`, `coverage/`, `data/`, `node_modules/`, `.next/`); solo `uis/backoffice/.env.example`, documentación sin secretos (`http://localhost:8000`) |
  | Enlaces relativos y anclas de los documentos tocados | 84 comprobados, 0 problemas |
  | Finales de línea | LF en todos los archivos tocados |

- **Demo de Supabase antes de la limpieza (lectura, 2026-10-21):** 6 activos, 5 entradas y 5 salidas (10 órdenes); stock 13/0/1/7/15/0. NXV-PER-001 tenía una entrada de 3 y dos salidas de 1, todas registradas por el usuario en sus pruebas (la segunda salida, después de verificar F5).
- **Limpieza (2026-10-21, autorizada por el usuario):**
  - **Demo de Supabase restaurada al neto del seed:** `TRUNCATE assets, asset_entries, asset_exits RESTART IDENTITY CASCADE` (antes 6/5/5, después 0/0/0) y `uv run --env-file .env seed-inventory --email diegoreynoso746@gmail.com` (código 0: 6 activos, 4 entradas y 3 salidas insertadas, a nombre de `45e456e9-…`). Comprobado en solo lectura: ids 1–6, stock 13/0/0/7/15/0, 4 entradas y 3 salidas (7 órdenes). *Corrige la nota de `techContext.md` de que la demo no estaba en el neto del seed.*
  - **Cuenta de prueba `ui-check-3533b06b@example.invalid` borrada** (variante B del usuario): `DELETE /users/03418547-…` con un token propio de esa cuenta, firmado en local con `JWT_SECRET_KEY` y de 2 minutos (nunca impreso), contra la API local → 204; repetido → 401. En `services/api/data/auth.json` ya no están ni el email, ni el id, ni su perfil (8 usuarios). El JSON no se editó a mano.

---

## 2026-10-20 — Frontend del inventario, F5: Historial (`/inventory/orders`)

**Estado: hecho, verificado por el usuario y comiteado**, en `feature/inventory-frontend`, sobre F4 (`a591686`). El agente no ha escrito en Supabase ni ha creado cuentas.

- **Verificación del usuario en el navegador, con Supabase real (2026-10-20), todo correcta:**
  - 9 órdenes: las 7 del seed más su entrada de 3 y su salida de 1 de NXV-PER-001, arriba del todo;
  - insignias Entrada/Salida distintas; activo con nombre y SKU; cantidad, oficina y detalle (proveedor / «Asignación → …» / «Consumo»); fecha legible en español y el `user_uuid` completo en todas;
  - sin botones de editar ni borrar;
  - con la API parada, error con «Reintentar»; al arrancarla, la tabla carga;
  - sin sesión, `/inventory/orders` lleva a `/login`.

- **Arquitectura:** `app/inventory/orders/page.tsx` (Server Component con metadata) → `components/inventory/order-history-view.tsx` (`'use client'`) → `hooks/use-inventory-orders.ts` (mismo patrón que `use-inventory-assets`: reducer, `ordersView`, sesión con abort y contador, y hook) → `listOrders`.
- **Tabla (`order-table.tsx`), de solo lectura y en el orden de la API** (la más reciente primero). Las columnas:
  - Tipo: `order-type-badge.tsx`, con icono, texto y color distintos (↓ Entrada en verde, ↑ Salida en azul);
  - Activo: nombre y SKU;
  - Cantidad y Oficina;
  - Detalle: «Proveedor: …» en una entrada; «Asignación → …» o «Consumo» en una salida;
  - Fecha: `Intl.DateTimeFormat('es-ES', { dateStyle: 'medium', timeStyle: 'short' })` en la zona del navegador, dentro de `<time dateTime>` con el ISO completo;
  - Usuario: el `user_uuid` completo, en monoespaciada y con `break-all`.
  - La clave de cada fila lleva el tipo, porque entradas y salidas tienen ids independientes.
- **`lib/order-format.ts`:** `ORDER_TYPE_BADGES`, `formatOrderDate` (una fecha que no se puede interpretar se muestra tal cual) y `orderDetail`.
- **Estados:** cargando; vacío («Todavía no hay entradas ni salidas.»); error con el `detail` de la API y «Reintentar»; datos, con el contador de órdenes (solo con datos: en el estado vacío no se muestra «0 órdenes»). Sin ninguna acción de editar ni borrar.
- **Tests:**
  - Jest: `__tests__/utils/order-format.test.ts`, en la cobertura (insignias distintas, fecha en `Europe/Madrid` y `America/New_York`, cambio de día, fecha no válida, los tres textos de Detalle);
  - `node:test`: `tests/use-inventory-orders.test.mjs` (los cuatro estados, con el 503 a través del servicio y el cliente reales; reintento; un fallo tras datos; recarga con abort; servicio que ignora la cancelación; desmontaje);
  - `production-source`: piezas; la vista solo usa su hook y nadie hace `fetch` (el hook solo toma `ApiAbortError` de `lib/api-client.ts`, como los de F2–F4); columnas del brief; `<time dateTime>`; `user_uuid` en monoespaciada con `break-all`; `relative overflow-x-auto`; colores distintos por tipo; ningún botón, enlace, formulario ni texto de editar o borrar en la tabla.
- **Mutaciones (7, todas detectadas y deshechas):** sin `user_uuid`; la misma insignia (texto e icono, y color); la fecha en ISO bruto (tabla y formato); un botón «Borrar»; sin descartar la respuesta tardía.
- **Comprobado en el navegador integrado** con un `fetch` falso dentro de la página (sin API real, sin Supabase y sin cuentas; el token falso se borró al terminar):
  - tres órdenes en el orden recibido, con los tres tipos de Detalle y fechas locales (`Europe/Madrid`: 23:30Z → «20 oct 2026, 1:30»);
  - estado vacío, error 503 con su `detail` y «Reintentar», que recupera los datos;
  - a 375 px no hay scroll horizontal en la página (375 = 375) y la tabla se desplaza en su contenedor (896 frente a 342).
- **Validación** (F4 → F5): `build` correcto, con `○ /inventory/orders`; `tsc` y `lint` sin errores; `node:test` 473 → 491; Jest 214 → 222.

---

## 2026-10-20 — Frontend del inventario, F4: Salida de activos (`/inventory/orders/outbound`)

**Estado: hecho, revisado por el usuario y comiteado**, en `feature/inventory-frontend`, sobre F3 (`064a569`). El agente no ha registrado salidas en Supabase ni ha creado cuentas.

- **Prueba del usuario en el navegador, con Supabase real (2026-10-20), todo correcta**, desde «Registrar salida» de la fila de Ratón ergonómico (`?asset_id=3`):
  - activo preseleccionado; Stock actual «3 · Bajo» visible antes de la cantidad; Oficina «Valencia» en solo lectura (el ajuste de F3);
  - al cambiar a NXV-IT-001 el stock pasa a 13 y al volver, a 3;
  - una asignación sin «Asignado a» da el error en ese campo, sin envío;
  - un consumo de 5: advertencia visible; al enviar, el 400 «Insufficient stock for asset 'Ratón ergonómico'. Available: 3, requested: 5.» bajo Cantidad;
  - un consumo de 1: «Salida registrada: 1 × Ratón ergonómico (NXV-PER-001)»; el ratón sigue elegido y el stock pasa a 2.
  - **Conclusión sobre F3:** el activo que se perdía tras la entrada no era un fallo; aquella página no llevaba `?asset_id=`.
  - La demo de Supabase sigue fuera del neto del seed (ahora con esta salida); se restaura en F6.

- **Página:** `app/inventory/orders/outbound/page.tsx`, Server Component asíncrono que lee `?asset_id=` como la entrada; `next typegen` regenera la ruta tipada nueva.
- **Hook (`hooks/use-outbound-form.ts`):**
  - el reducer guarda el activo elegido y el stock (`idle` / `loading` con el valor anterior / `known` / `error`), además del envío y `formKey`;
  - `selectAsset` lee `GET /inventory/products/{id}`, aborta la lectura anterior y descarta las respuestas tardías (contador; vale también con A → B → A y con un servicio que ignora la cancelación);
  - `submit(values, nextAssetId)`: un envío a la vez; tras el éxito el formulario se monta limpio con el activo de la URL (`formInitialAssetId`) y se vuelve a leer su stock; tras un 400 `insufficient_stock` se vuelve a leer el del activo elegido, sin vaciar el valor que se muestra;
  - funciones puras: `knownStock`, `quantityEnabled`, `outboundFormValues` («Asignado a» vacío salvo con `allocation`) y `outboundConfirmation` («Salida registrada: N × nombre (SKU)»).
- **Formulario (`components/inventory/outbound-form.tsx`), en este orden:**
  1. Activo (`AssetSelect` compartido);
  2. Stock actual (`ReadOnlyField`: «Consultando stock…» con spinner, o el número con `StockLevelBadge`; si falla, «No disponible» y el aviso «No se pudo consultar el stock…»);
  3. Oficina (`ReadOnlyField`);
  4. Tipo de salida (radios «Asignación» / «Consumo», que envían `allocation` / `consumption`);
  5. Asignado a (solo con una asignación);
  6. Cantidad: deshabilitada hasta conocer el stock (o hasta que falle su lectura); la advertencia de cantidad mayor que el stock va en un contenedor `aria-live="polite"` y no bloquea el envío; el 400 de stock va debajo con el `detail` de la API y `role="alert"` (prop nueva `alert` de `FieldMessages`).
  - Con un consumo, los errores de `assigned_to` (que no se ve) van al aviso general.
- **`lib/stock-check.ts`:** `exceedsStock(quantity, stock)`, probado con Jest (`__tests__/utils/stock-check.test.ts`, en la cobertura de `jest.config.mjs`).
- **Tests:**
  - `tests/inventory-outbound.test.mjs` (19): Cantidad y stock; lectura al elegir; A → B con abort; servicio que ignora la cancelación (A → B y A → B → A); fallo de la lectura; sin activo; advertencia sin bloqueo; «Asignado a» en los valores y en el body (`null` en un consumo); validación sin petición; 400 junto a Cantidad y nueva lectura; 422 de `assigned_to`; 404 en el aviso general; éxito con y sin activo en la URL; doble envío; desmontaje;
  - `production-source`: piezas, la vista solo usa hooks y elige el activo de la URL también tras el éxito, selector compartido sin `<option>` propios, orden de los campos, Stock y Oficina en solo lectura, Cantidad ligada a `quantityEnabled`, `aria-live`, `role="alert"` en el 400, la advertencia fuera de `handleSubmit` y «Asignado a» solo con `allocation`.
- **Mutaciones (13, todas detectadas y deshechas):** sin abortar la lectura anterior; sin descartar la respuesta tardía (detectada tras añadir el test A → B → A, porque la guarda del reducer la tapaba con A ≠ B); la advertencia bloquea el envío; el 400 fuera de Cantidad (servicio) y sin `role="alert"`; `assigned_to` en un consumo (body y valores); sin volver a leer el stock tras el éxito y tras el 400; Cantidad habilitada sin stock (regla y formulario); sin el activo de la URL tras el éxito.
- **Comprobado en el navegador integrado** con un `fetch` falso dentro de la página (sesión, activos, stock y salidas simulados; sin API real, sin Supabase y sin cuentas; el token falso se borró al terminar):
  - preselección y stock (8, «Suficiente»); al cambiar de activo, «Consultando stock…» con Cantidad deshabilitada;
  - stock 0 con cantidad 3: advertencia visible y envío permitido; el 400 aparece bajo Cantidad con `role="alert"` y sin aviso general, y el stock se vuelve a leer («Actualizando…»);
  - salida correcta con asignación: confirmación, formulario limpio con el activo de la URL y stock leído de nuevo (8 → 6);
  - lectura fallida: «No disponible», el aviso y Cantidad habilitada;
  - a 375 px no hay scroll horizontal (375 = 375).
- **Validación** (F3 → F4): `build` correcto, con `ƒ /inventory/orders/outbound`; `tsc` y `lint` sin errores; `node:test` 445 → 473; Jest 201 → 214.

---

## 2026-10-20 — Frontend del inventario, F3: Entrada de activos (`/inventory/orders/inbound`)

**Estado: hecho, revisado por el usuario y comiteado**, en `feature/inventory-frontend`, sobre F2 (`72bd839`). El agente no ha registrado ninguna entrada en Supabase ni ha creado cuentas.

- **Demo de Supabase fuera del neto del seed:** la prueba real del usuario dejó una entrada de 3 × NXV-PER-001. Se restaura en F6 (TRUNCATE + `seed-inventory`, con confirmación del usuario).
- **Verificación en el navegador del usuario (2026-10-20):**
  - sin enviar: el selector muestra las 6 opciones «nombre — SKU (oficina)», sin ids; la Oficina cambia con el activo; la preselección funciona desde la fila de Activos; con `?asset_id=999` aparece el aviso, sin preselección; el formulario vacío da errores por campo y ninguna petición;
  - entrada real «Entrada registrada: 3 × Ratón ergonómico (NXV-PER-001)»: en Activos, 3 y «Bajo». Cantidad y Proveedor se vaciaron, pero el activo volvió a «Elige un activo…».
- **Investigación del activo perdido:**
  - el enlace de la fila es correcto (`inboundOrderHref(asset.id)` → `?asset_id=N`; comprobado en los `href`);
  - en el navegador integrado, con un `fetch` falso dentro de la página (sin API, sin Supabase y sin cuentas): desde «Registrar entrada» de la fila (`?asset_id=2`), el activo **se mantiene** tras la entrada; desde la subnavegación (sin parámetro), vuelve a «Elige un activo…», que es el síntoma observado;
  - el agente no pudo ver la URL del navegador del usuario (el log de Next no guarda las URLs), y la causa más probable es que la página no llevaba `?asset_id=`;
  - aun así, el comportamiento queda fijado: `formInitialAssetId(preselección)` en `lib/asset-preselection.ts` (también la usará F4), un test que lo comprueba tras una entrada correcta, una regla estática en la vista y dos mutaciones detectadas.
- **Oficina de solo lectura:** `components/inventory/read-only-field.tsx` es un `<output>` asociado a la etiqueta, con fondo atenuado y sin borde de campo. Se mantienen la ayuda y «Se toma del activo elegido» cuando no hay activo, y lo usará F4 (Stock actual y Oficina). La regla estática exige `ReadOnlyField` y ni `<input>` ni borde; detecta las mutaciones «otra vez input» y «con borde».

- **Página:** `app/inventory/orders/inbound/page.tsx`, Server Component asíncrono (`PageProps<'/inventory/orders/inbound'>` de Next 16: `searchParams` es una promesa, así que la ruta es dinámica). Lee `?asset_id=` con `parseAssetIdParam` y renderiza `inbound-form-view.tsx`.
- **Piezas:**
  - `lib/asset-preselection.ts`: lectura de `?asset_id=` (solo un entero positivo en dígitos; cualquier otra cosa cuenta como pedido inválido), `resolvePreselection` (none / pending / found / missing) y `assetOptionLabel` («nombre — SKU (oficina)», sin id);
  - `lib/inventory-form-errors.ts`: reparto de un error entre los campos y el aviso general (422 y validación en cliente por campo, con el `msg` de la API debajo; `api_error` con campo del formulario solo junto al campo; el resto, aviso general). Lo reutilizará la salida (F4);
  - `hooks/use-inbound-form.ts`: reducer (`formKey + 1` tras el éxito), sesión sin React (un envío a la vez; el segundo se ignora; abort al desmontar) y hook; `inboundConfirmation` → «Entrada registrada: N × nombre (SKU)»;
  - `components/inventory/asset-select.tsx` (cargando, error con «Reintentar», vacío y datos; aviso visible si el activo del enlace no existe), `field-messages.tsx` e `inbound-form.tsx` (oficina del activo en solo lectura, `inputMode="numeric"`, botón con spinner y deshabilitado durante el envío, foco al aviso general tras un fallo).
- **Tests:** `tests/inventory-inbound.test.mjs` (14: parámetro, preselección, opción sin id, reparto de errores, éxito y `formKey`, body con números y la oficina del activo, validación sin petición, 400/404/500/503 con `detail`, 422 con `apiMessage`, red/timeout/respuesta ilegible, doble envío y desmontaje). `production-source`, 4 reglas F3: piezas presentes; el selector nunca muestra el id; la vista solo usa sus hooks y ninguna pieza del inventario hace `fetch` ni importa un cliente HTTP; oficina en solo lectura, botón con `isLoading` y `key` con `formKey`.
- **Regla estática ajustada:** «el inventario usa su propio cliente» prohibía cualquier literal `/inventory/(products|orders)` fuera del servicio y fallaba con `PageProps<'/inventory/orders/inbound'>`, el tipo de ruta que genera Next para las props de la página (no una URL de la API). Ahora ignora solo el argumento de `PageProps<'…'>`/`LayoutProps<'…'>`; una URL de la API en una página se sigue detectando (mutación 7).
- **Mutaciones (12, todas detectadas y deshechas):** el selector muestra el id (opción y etiqueta); oficina editable y oficina enviada que no es la del activo; `quantity` como texto; sin limpiar tras el éxito (reducer y `key`); error sin su `detail` (servicio y texto); doble envío (sesión y botón sin `isLoading`); una URL de la API en la página.
- **Validación** (F2 → F3, con los ajustes): `build` correcto, con `ƒ /inventory/orders/inbound`; `tsc` y `lint` sin errores; `node:test` 416 → 445; Jest 201 (sin cambios).

---

## 2026-10-20 — Frontend del inventario, F2: Activos (`/inventory/products`) y navegación

**Estado: hecho y validado; comiteado tras la revisión del usuario**, en `feature/inventory-frontend`, sobre F1 (`0e0f133`) y el `style(api)` (`2dccef0`). Sin pruebas que escriban en Supabase: el usuario hace las del navegador.

- **Antes, ya comiteado:**
  - F1 + el brief literal (`docs/inventory-frontend-brief.md`), commit `0e0f133`;
  - la unión de los imports de `typing` en `services/api/app/modules/inventory/router.py`, commit `2dccef0`. Las suites de `services/api` dan 409 y 612 antes y después; pytest cuenta un subtest menos, porque `test_no_session_is_created_at_module_level` abre uno por sentencia de nivel de módulo.
- **Navegación:**
  - `app/inventory/layout.tsx` con `components/inventory/inventory-nav.tsx` (Activos · Entrada de activos · Salida de activos · Historial, con `aria-current` vía `NavLink`);
  - un solo enlace «Inventario» en la cabecera, marcado en todo `/inventory` (prop nueva `activePrefix` de `NavLink`);
  - `app/inventory/page.tsx` redirige a `/inventory/products` con `redirect()` de Next 16 (Server Component).
- **`/inventory/products`:**
  - página Server Component → `asset-list-view.tsx` → `hooks/use-inventory-assets.ts` (reducer, sesión y hook);
  - tabla Nombre / SKU / Categoría / Oficina / Stock actual (número + `StockLevelBadge` con color, icono y texto) y, en cada fila, «Registrar entrada» y «Registrar salida» con `?asset_id=`;
  - cuatro estados (cargando, error con «Reintentar», vacío sin tabla, datos); `relative overflow-x-auto`.
- **Errores:** los textos se movieron a `lib/inventory-error-copy.ts` (módulo puro y probado). Un `api_error` muestra el `detail` de la API bajo un título en español; el resto, textos fijos.
- **`lib/stock-level.ts`:** 0 = Agotado; de 1 a 5 = Bajo; más de 5 = Suficiente (D6), documentado.
- **Tests:**
  - Jest: `stock-level` (0, 1, 5, 6…) y las rutas `/inventory/*` en `auth-routes`;
  - `node:test`: `use-inventory.test.mjs` (los cuatro estados, reintento, carrera con abort y con un servicio que ignora la cancelación, desmontaje y los textos de error);
  - `production-source`: estructura, Server/Client Components, redirección, subnavegación, un solo enlace en la cabecera, las acciones de cada fila y nada de «productos» en la UI.
- **Mutaciones:**
  - detectadas: umbrales de `stockLevel` (`<` y `0`); no descartar respuestas antiguas; no abortar la carga anterior; las dos acciones de la fila a la entrada; «Inventario» sin `activePrefix`; el error sin su `detail`; la vista sin `'use client'`;
  - **no detectada, equivalente:** quitar la guarda `active` de `emit` (todos los que llaman ya comprueban `active`).
- **Ajustes de la revisión visual del usuario:**
  - el SKU nunca se parte (`whitespace-nowrap`);
  - el número y el indicador del stock van en una línea en todas las filas;
  - un solo título: el `h1` de la página, que pasa su id a la sección (`aria-labelledby`) como prop, porque una constante importada de un módulo `'use client'` en un Server Component no es el texto.
- **Comprobado en el navegador** (con una cuenta de prueba local `ui-check-…@example.invalid`, creada en `/register` y guardada en `services/api/data/auth.json`; solo lecturas de Supabase):
  - a 1280 px y a 375 px no hay scroll horizontal en la página (1265 = 1265 y 375 = 375);
  - a 375 px la tabla se desplaza dentro de su contenedor (704 frente a 342) y la subnavegación cabe;
  - el SKU ocupa una línea y la celda del stock mide lo mismo en las 6 filas;
  - sin sesión, `/inventory/products` lleva a `/login`.
- **422, opción 3 del usuario:** `InventoryFieldError.apiMessage` lleva el `msg` de la API (sin prefijo, texto no vacío de hasta 300 caracteres) para mostrarlo debajo del texto propio. Lo cubren 3 tests nuevos; las mutaciones (sin `apiMessage`, sin quitar el prefijo, sin límite) se detectan.
- **Validación** (F1 → F2): `build` correcto, con `/inventory` y `/inventory/products`; `tsc` y `lint` sin errores; `node:test` 386 → 416; Jest 187 → 201.

---

## 2026-10-19 — Frontend del inventario (`uis/backoffice`), F1: memory-bank, contrato, cliente y servicio

**Estado: hecho y validado** (el usuario revisa cada fase). ~~Sin comitear.~~ *Corregido el 2026-10-21: comiteado en `0e0f133` e integrado en `main` con la PR #22 (merge `410da71`).* En `feature/inventory-frontend`, creada desde `origin/main` en `8e5448e` (merge de la PR #21). Plan aprobado por el usuario: F1 (integración, sin UI), F2 (Activos, subnavegación y `/inventory` → `/inventory/products`), F3 (Entrada), F4 (Salida), F5 (Historial) y F6 (cierre y restauración de la demo).

- **Memory-bank:** sincronizado con el merge de la PR #21 (`8e5448e`, 2026-10-19). El inventario ya no figura como «pendiente de PR» ni en una rama sin integrar; `origin/main` se verificó en `8e5448e` (también la PR #20, `ef1e083`).
- **`uis/backoffice/CLAUDE.md`:** quinta pieza (`/inventory/*`, autorizada por el usuario) y su sección:
  - páginas y navegación (un enlace «Inventario» en la cabecera y una subnavegación en `app/inventory/layout.tsx`);
  - `NEXT_PUBLIC_INVENTORY_API_URL` sin reserva;
  - vocabulario y etiquetas del CONTEXT;
  - formularios (oficina del activo, números, `?asset_id=`, cantidad bloqueada hasta conocer el stock, advertencia que no bloquea);
  - la excepción de errores acotada a `/inventory`: el `detail` de texto de los 4xx/5xx se muestra; sin cuerpo legible, textos fijos; 422 con texto propio por campo; 401 como siempre.
- **Código** (sin UI todavía):
  - `types/inventory.ts`: contrato y vocabulario.
  - `services/normalizers.ts`: activos, órdenes discriminadas por `type`, campos de los 422.
  - `lib/inventory-api-client.ts`: el mismo `createApiClient` con la base URL de `NEXT_PUBLIC_INVENTORY_API_URL`.
  - `lib/api-client.ts`: `ApiConfigError` nombra la variable del cliente (mensaje que la UI no muestra).
  - `services/inventory.service.ts` y `lib/inventory-routes.ts`.
  - `.env.example` con la variable nueva.
- **Tests:**
  - `node:test`: `inventory-contract` (vocabulario igual al CONTEXT y a `vocabulary.py`, límites, las 4 rutas protegidas) y `inventory.service` (Bearer en las 5 operaciones, variable sin reserva, números, oficina del activo, `assigned_to: null` en un consumo, y todos los errores, incluidos 500/503 con `detail` y el `detail` que no es texto); dos reglas nuevas en `production-source`.
  - Jest: `__tests__/utils/inventory.service.test.ts` (`parseQuantity` y validadores).
- **Mutaciones**, todas detectadas y deshechas: sin Bearer; `quantity` como texto; `office` del formulario en vez del activo (en la entrada y, tras reforzar el test con un activo de Miami, en la salida); `insufficient_stock` sin `field`; reserva a `NEXT_PUBLIC_API_URL`.
- **Validación** (línea base → F1): `build` correcto; `tsc` y `lint` sin errores; `node:test` 344 → 386; Jest 161 → 187.
- **Brief literal versionado** en `docs/inventory-frontend-brief.md`, con una nota de equivalencias («BRIEFING.md» = `README.md` raíz + CONTEXT; `/backoffice/inventory/...` = `/inventory/...`), y enlazado desde `uis/backoffice/CLAUDE.md`.
- **422 (corregido el 2026-10-20, opción 3 del usuario):** junto a cada campo, un texto propio en español y, debajo, el `msg` de la API si es utilizable. Así se cumple también el «extrae el mensaje del cuerpo» del brief.

---

## 2026-10-18 — Hito 5, F5: documentación de cierre y verificación final (hito hecho)

**Estado: hecho y verificado, sin comitear** (el usuario revisa antes del commit), en `feature/inventory-orm`, sobre F4 (`f004944`). **El Hito 5 (F1–F5) está hecho.** ~~Pendiente: commit de F5, push y PR, que hace el usuario.~~ *Corregido el 2026-10-19: comiteado, PR #21 integrada en `main` (merge `8e5448e`).*

- **Documentación:**
  - `services/api/SPECS.md`: Parte F (§34–§40) con requisitos, decisiones D1–D11 y F2–F4, equivalencia con los nombres del enunciado, contrato, errores y esquema; referencias en la cabecera, §4 y §7.
  - `services/api/README.md`: sección «Inventario (Hito 5)» (Supabase y Transaction pooler, `DATABASE_URL`, arranque, seed con su salida y endpoints); también la tabla general de endpoints, la configuración, los tests y la estructura.
  - `services/api/TESTING.md`: §13 (qué cubre, cómo ejecutarlo y las mutaciones); el título pasa a cubrir todas las baterías.
  - `docs/local-development.md`: `DATABASE_URL` en el arranque y en las variables.
  - `AGENTS.md` §4: bloque «Inventario (Hito 5)».
  - **Nuevo:** `docs/inventory-review.md`, guía de revisión con trazabilidad, comandos de PowerShell, recorrido en `/docs`, RLS en Supabase y lo no verificado.
  - **Memory-bank:** `techContext.md` (fila del inventario y decisión «Inventario: doble base de datos»; el recuento de la suite `unittest` pasa a 406) y `projectbrief.md` (fila de Tecnología, Sergio Molina, NXV-0201, solo con datos del CONTEXT).
- **Errores en OpenAPI** (pedido en la revisión de F5):
  - `router.py` documenta con `responses=` los errores reales de cada ruta, con el schema `ErrorResponse` (`{detail, code}`, en `schemas.py`), una descripción y ejemplos construidos con los errores de `core/errors.py`;
  - el 400 de la salida lleva dos ejemplos, `office_mismatch` e `insufficient_stock` (mensaje literal);
  - el comportamiento no cambia;
  - 3 tests nuevos (`OpenApiErrorsTests`) leen `/openapi.json`; dos mutaciones (sin el 503 común, sin el ejemplo de stock) detectadas y deshechas;
  - mencionado en `SPECS.md` §38 y en la guía.
- **Arreglo menor:** `services/api/app/core/errors.py` había perdido el salto de línea final en F2. Por eso `git diff main..HEAD --stat` daba una línea más sin `--ignore-cr-at-eol`. Se restaura.
- **Verificación final** (2026-10-18):

| Comprobación | Resultado |
|---|---|
| `services/api`: `unittest` (`AGENTS.md` §4) | 409 OK (312 + 97 del inventario), sin `ResourceWarning` |
| `services/api`: `uv run --no-sync python -m pytest` | 612 OK (515 + 97) |
| `packages/shared` | 81 OK (sin cambios en la rama) |
| `packages/incident-analyzer` | 121 OK, 7 omitidos (sin cambios en la rama) |
| `git diff main --stat`, con y sin `--ignore-cr-at-eol` | idéntico (34 archivos con F5) |
| Secretos en `git log -p main..HEAD` y en `git diff main` | no encontrados: ni el project-ref de Supabase, ni el usuario, la contraseña o el host del pooler, ni la `DATABASE_URL`, ni `JWT_SECRET_KEY`, ni ningún `*.pooler.supabase.com`. Las URL `postgresql://usuario:contraseña@` que aparecen son placeholders o fixtures ficticios |
| `.env`, `.vscode/`, `.coverage` o `data/` en algún commit de la rama | ninguno |
| Enlaces relativos (y anclas) de los 9 documentos tocados | 103 comprobados, 0 rotos |

- **Verificación manual del usuario (2026-10-18):** recorrido en `/docs` contra Supabase, con un login real (*Authorize* con su cuenta; `user_uuid` `45e456e9-…`).
  - `GET /inventory/products` → 200, ids 1–6 y stock 13/0/0/7/15/0;
  - salida de 20 de `asset_id` 1 → 400 `insufficient_stock` con `Available: 13, requested: 20.`;
  - `allocation` sin `assigned_to` → 422 con `loc` `["body", "assigned_to"]`;
  - `GET /inventory/orders` → 200, 7 órdenes con su `user_uuid`;
  - tras reiniciar, `/docs` muestra documentados los errores de las rutas (400/404/401).
  - No registró ninguna orden válida: el neto del seed sigue intacto.
  - En `docs/inventory-review.md` quedan fuera de «lo no verificado» el recorrido en Swagger y el login real.
- **Datos de la demo en Supabase:** cargados con el seed en F4 y no se tocan.
- **Problema conocido:** `docs/context-nexova-gestion-inventario-hito-5.md` no termina en salto de línea; se dejó tal cual porque es el CONTEXT original.

---

## 2026-10-18 — Hito 5, F4: seed `uv run seed-inventory --email …` y `dispose()` del motor

**Estado: hecho y validado, sin comitear** (el usuario revisa cada fase), en `feature/inventory-orm`, sobre F3b (`a9a3fdb`). Siguiente: F5 (documentación de cierre).

- **`app/modules/inventory/seed.py`**, entry point `seed-inventory` en `pyproject.toml`, añadido a `PRINT_ALLOWED` en `test_architecture.py` (mismo motivo que `app/seed.py`).
  - **Datos:** los 6 activos literales del CONTEXT. Las entradas (10 y 5 de `NXV-IT-001`, 8 de `NXV-PER-002`, 20 de `NXV-OFF-001`) y las salidas (2 + 5 + 1) las aprobó el usuario.
  - **Empleados:** `EMPLEADO-FICTICIO-01` y `-02` están documentados en el código como identificadores ficticios, porque el CONTEXT no da empleados.
  - **Neto:** 13/0/0/7/15/0.
  - **Usuario:** se busca por `--email` en TinyDB, normalizado como en el login. El `user_uuid` de las órdenes es su `id`.
  - **Una sola transacción:**
    - activos idempotentes por `sku`;
    - las órdenes de un activo solo se insertan si no tiene ninguna;
    - las órdenes pasan por los schemas de la API y por `service.add_inbound_order` / `add_outbound_order` (sin commit por orden), así que la regla del stock no se reimplementa.
    - Un dato que la API rechazaría → código 1 y no se escribe nada.
  - **Códigos de salida:**
    - 1: configuración (sin `DATABASE_URL`, esquema inválido o falta `--email`, que argparse terminaría con 2), usuario inexistente o inactivo (sin repetir el email), o datos semilla rechazados;
    - 2: base no disponible (Supabase o el TinyDB de usuarios), solo con la clase del error y sin traceback.
- **`service.py`:** la lógica de las órdenes se separa del commit: `add_inbound_order` y `add_outbound_order` hacen `flush` sin commit. `create_*_order` las usan y confirman. Las rutas no cambian.
- **`dispose()`:** el lifespan libera el motor al cerrar, también tras un arranque fallido. Los tests de F2 que usan una app sin lifespan lo liberan con `addCleanup`. Ya no queda ningún `ResourceWarning: unclosed database` en la suite.
- **Tests:** 14 nuevos (13 en `tests/test_inventory_seed.py` y 1 del `dispose`).
  - dos ejecuciones (6/4/3 y luego 0);
  - activo existente con órdenes;
  - datos que rompen el stock → nada escrito;
  - email inexistente, inválido o inactivo → 1;
  - sin `DATABASE_URL` o con otro esquema → 1;
  - base caída → 2, también lanzando el comando en un subproceso;
  - `auth.json` ilegible → 2;
  - `GET /inventory/products` exacto tras el seed (caso del evaluador) y 7 órdenes con el `user_uuid` del usuario.
  - El test de F2 que vigila dónde se abren sesiones admite ahora `seed.py:_seed_database`.
- **Mutaciones**, todas detectadas y deshechas: seed sin buscar el SKU; salidas sin la regla del stock; órdenes duplicadas en la segunda ejecución; lifespan sin `dispose()`.
- **Supabase real** (datos de la demo, **no se borran**):
  - `uv run --env-file .env seed-inventory --email <usuario>` dos veces: 6/0/4/3 y después 0/6/0/0.
  - `uv run` reconstruyó el paquete para crear el entry point; `pip list` no cambió.
  - Con la API arrancada y un JWT del mismo usuario: `GET /inventory/products` → ids 1..6 y stock 13/0/0/7/15/0; `GET /inventory/orders` → 7 órdenes, todas con su `user_uuid`.
  - `data/auth.json` se usó solo para leer (el sha256 no cambió).
- **Validación:**
  - `unittest`: 406 OK (392 + 14).
  - `uv run --no-sync python -m pytest`: 609 OK (595 + 14).

---

## 2026-10-18 — Hito 5, F3b: órdenes de entrada y salida, regla del stock y `GET /inventory/orders`

**Estado: hecho y validado, sin comitear** (el usuario revisa cada fase), en `feature/inventory-orm`, sobre F3a (`c3fc7bf`). Siguiente: F4 (seed).

- **Antes, en F3a (ya comiteada):** la ruta por id se publica como `/inventory/products/{id}`, con un test sobre `/openapi.json`.
- **Base de Supabase:** reiniciada una vez con `TRUNCATE assets, asset_entries, asset_exits RESTART IDENTITY CASCADE`, con autorización del usuario y las tablas ya vacías. Se hizo con un script fuera del repo.
- **Schemas** (`schemas.py`):
  - `InboundOrderCreate` y `OutboundOrderCreate`: `extra="forbid"`, así que `user_uuid` en el body da 422.
  - `quantity`: entero estricto entre 1 y 2147483647. `asset_id`: entero estricto.
  - La coherencia de `assigned_to` es un `field_validator` que lee `exit_type` de `info.data`, con `validate_default=True`: el 422 sale con `loc` `["body", "assigned_to"]`, también cuando el campo falta.
  - Respuestas: `InboundOrderRead` y `OutboundOrderRead` (`type` literal, activo embebido `AssetSummary`, `created_at` con zona) y `OrderRead`, la unión discriminada por `type`.
  - `QUANTITY_MAX` va en `vocabulary.py`.
- **Service** (`service.py`):
  - `user_uuid` es el `id` del usuario de `get_current_user`, declarado en la ruta (FastAPI lo resuelve una sola vez por petición).
  - **Entrada:** 404 `asset_not_found` → 400 `office_mismatch` → insertar.
  - **Salida:** `locked_asset_query` (`SELECT … FOR UPDATE`) → 404 → oficina → stock → 400 `insufficient_stock` con el mensaje literal del CONTEXT → insertar y commit, todo en la misma transacción. Si algo falla no se hace commit y `get_db` cierra la sesión.
  - **`GET /orders`:** dos consultas con JOIN a `assets`, ordenadas por `created_at` descendente; a igual fecha, salidas antes que entradas y, dentro de cada tipo, `id` descendente. `created_at` sale siempre en UTC, también desde SQLite.
  - Errores nuevos `OfficeMismatchError` e `InsufficientStockError`, en `core/errors.py`.
- **Tests:**
  - 24 nuevos, en `tests/test_inventory_orders.py`.
  - `InventoryTestCase` pasa a `tests/inventory_support.py`, compartido con `test_inventory_products.py`.
  - El test de «ningún ORM» cubre ahora las 6 rutas y despliega `list[...]`, uniones y `Annotated`.
- **Mutaciones**, todas detectadas y deshechas:
  - sin `FOR UPDATE`;
  - el stock comprobado después de insertar;
  - `>=` en vez de `>` (salida igual al stock rechazada);
  - sin comprobar la oficina, en la salida y en la entrada;
  - `user_uuid` tomado del body;
  - N+1 en `GET /orders`;
  - el validador de `assigned_to` sobre el body.
- **Supabase real** (usuario temporal en una TinyDB temporal):
  - entrada de 5; salida de 7 → 400 con el mensaje exacto; `allocation` de 3 → 201;
  - stock 2 y `GET /orders` con 2 órdenes;
  - **concurrencia:** dos salidas de 5 a la vez sobre un stock de 5 → una 201 y una 400 `Available: 0`. La segunda esperó al bloqueo y vio el stock que dejó la primera.
  - Después se borró todo lo creado y se volvió a hacer `TRUNCATE … RESTART IDENTITY`: la base queda vacía, con los ids desde 1 para el seed.
- **Validación:**
  - `unittest`: 392 OK (368 + 24).
  - `uv run --no-sync python -m pytest`: 595 OK (571 + 24).

---

## 2026-10-18 — Hito 5, F3a: schemas, `service.py` y rutas de productos

**Estado: hecho y validado, sin comitear** (el usuario revisa cada fase), en `feature/inventory-orm`, sobre F2 (`d68d93e`). Quedan las órdenes para F3b.

- **`vocabulary.py`:** `AssetCategory`, `Office`, `ExitType`, `TEXT_MAX_LENGTH` y `USER_UUID_LENGTH`, importados por `models.py` y por `schemas.py`. Así `schemas.py` no importa `models.py`, y un test lo vigila.
- **`schemas.py`:** Pydantic puro.
  - `AssetCreate`: `extra="forbid"`; textos sin espacios en los extremos, no vacíos y de 200 caracteres como máximo; vocabulario cerrado.
  - `AssetRead`: añade `current_stock`.
- **`service.py`:**
  - el stock se calcula en la misma consulta que lee los activos: subconsultas agregadas por `asset_id`, `LEFT JOIN` y `COALESCE`, ordenado por `id`;
  - activo inexistente → 404 `asset_not_found`;
  - el alta comprueba antes el SKU y, si el `UNIQUE` lanza `IntegrityError` en el commit, hace rollback, vuelve a comprobar y responde 409 `sku_already_exists`. Cualquier otro `IntegrityError` sigue siendo el 500 opaco.
  - Los errores nuevos están en `core/errors.py` con mensajes fijos (no repiten el SKU).
- **`router.py`:**
  - `APIRouter(prefix="/inventory", tags=["inventory"])` con `GET` y `POST /inventory/products` y `GET /inventory/products/{id}` (el parámetro se llama `id`, como en el enunciado, también en OpenAPI; un test lo comprueba);
  - `response_model` en todas, sesión por `Depends(get_db)`;
  - registrado en `main.py` con `dependencies=authenticated`.
- **Tests:** 20, en `tests/test_inventory_products.py`, con `with TestClient`.
  - Casos felices, 401 en las 3 rutas, 404, 409 (también la carrera simulada) y 422 (vocabulario, extras, `current_stock`, textos).
  - Stock: 10 + 5 − 2 − 1 = 12. Un JOIN sin agregar daría 24.
  - Consultas: una sola, igual con 1 y con 20 activos con órdenes.
  - Ningún `response_model` hereda de SQLModel.
  - FastAPI 0.141 guarda los routers incluidos como `_IncludedRouter` en `app.routes`, así que el test recorre `inventory_router.routes` y comprueba las rutas publicadas en `/openapi.json`, que deben ser exactamente `/inventory/products/{id}`.
- **Mutaciones**, todas detectadas y deshechas: JOIN sin agregar antes; N+1 (stock por activo en un bucle); sin capturar el `IntegrityError`; sin `extra="forbid"`; ruta que devuelve el ORM; sin `COALESCE`; router sin JWT.
- **Supabase real:**
  - `POST` de un activo de prueba → 201 con `current_stock: 0`;
  - `GET` por id y el listado → stock 0;
  - el `POST` repetido → 409 y sin token → 401;
  - después se borró con SQL: 0 activos y 0 órdenes en la base.
  - **Problema conocido:** la secuencia de `assets.id` ya avanzó, así que el primer activo del seed no tendrá `id = 1`.
- **Validación:**
  - `unittest`: 368 OK (348 + 20).
  - `uv run --no-sync python -m pytest`: 571 OK (551 + 20).

---

## 2026-10-18 — Hito 5, F2: configuración, motor, `get_db`, modelos ORM, lifespan (tablas + RLS) y 503

**Estado: hecho y validado, sin comitear** (el usuario revisa cada fase), en `feature/inventory-orm`, sobre F1 (`6b977af`). Todavía no hay rutas `/inventory` (F3a y F3b).

- **Configuración** (`app/core/config.py`):
  - `DATABASE_URL` obligatoria al arrancar: `require_database()`, que `create_app` llama después de `require_auth()`.
  - `repr=False` y `ConfigError` sin repetir la URL.
  - El esquema se valida solo en `from_env` (`postgresql://` y `postgresql+psycopg2://`), así que los tests inyectan `Settings(database_url="sqlite://")`.
- **`app/modules/inventory/database.py`:**
  - `build_engine`, un motor por app en `app.state.inventory_engine`, sin motor ni sesión a nivel de módulo.
    - **Postgres:** `NullPool`, `connect_timeout=5`, `hide_parameters=True`.
    - **Driver:** `postgresql://` pasa a `postgresql+psycopg2` con `make_url`, porque SQLAlchemy 2.1 usa psycopg v3 por defecto.
    - **SQLite:** `StaticPool` y `PRAGMA foreign_keys=ON`.
    - **URL ilegible:** `ConfigError` sin la URL y sin encadenar la excepción.
  - `init_db`: `create_all` y luego `ALTER TABLE … ENABLE ROW LEVEL SECURITY` en las tres tablas, solo en Postgres, en una transacción. Es idempotente.
  - `inventory_lifespan` lo ejecuta al arrancar. Si falla, `init_db` lanza `InventoryStartupError` con un mensaje fijo (`inventory database is unavailable at startup: <Clase>`). Se lanza fuera del `except`, sin `__cause__` ni `__context__`, con el mismo patrón que `GuardedJSONStorage` (A2).
  - uvicorn imprime la traza de esa excepción, sin la original, y termina con código 3 (`STARTUP_FAILURE`).
  - *Una primera versión usaba `os._exit(1)`; el usuario la rechazó en la revisión porque mata cualquier proceso que ejecute el lifespan, como pytest o `with TestClient`.*
  - `get_db`: una `Session` por petición.
- **`models.py`:**
  - `Asset`, `AssetEntry` y `AssetExit` (tablas `assets`, `asset_entries` y `asset_exits`).
  - FK con índice en `asset_id`, `UNIQUE` global en `sku`, `TIMESTAMPTZ` y vocabulario en VARCHAR (sin ENUM nativos).
  - `CHECK` de `quantity > 0`, del vocabulario y de la coherencia de `assigned_to`.
  - Sin tabla de usuarios.
- **503** (`app/core/errors.py`):
  - `OperationalError`, `InterfaceError` y `TimeoutError` de SQLAlchemy → 503 `storage_unavailable`;
  - el log solo lleva `storage inventory is unavailable: <Clase>`;
  - el resto de errores de la base siguen siendo el 500 opaco.
- **Soporte de tests, cambio mínimo:** `TEST_DATABASE_URL = "sqlite://"` en `tests/support.py`, en `with_test_auth`, en `AuthTestCase` y en `AuthConfigTests.valid()`. Los clientes existentes no usan `with TestClient`: no ejecutan el lifespan ni tocan la base.
- **Tests nuevos:** 36, en `tests/test_inventory_database.py` y `tests/test_inventory_startup.py`.
  - **En proceso:** `with TestClient(app)` con la base caída lanza `InventoryStartupError` sin encadenar, y después otra app arranca en el mismo proceso.
  - **Con uvicorn real** contra un puerto local cerrado: código 3, y la salida no lleva usuario, contraseña, host, base, `postgresql://`, `psycopg2` ni la excepción original.
  - **Mutaciones**, todas detectadas y deshechas: sin `PRAGMA`; sin la llamada a RLS en `init_db`; sin el `ALTER`; con una sesión a nivel de módulo; con una sesión cacheada en `get_db`; sin forzar psycopg2; `InventoryStartupError` lanzada dentro del `except` (uvicorn imprime entonces `localhost` y `psycopg2`).
- **Supabase real:**
  - antes del arranque, las tres tablas no existían;
  - tras `uv run --env-file .env uvicorn app.main:create_app --factory`, existen con `relrowsecurity=True`, `relforcerowsecurity=False` y 0 políticas;
  - un segundo arranque también termina bien (idempotente).
- **Sin `DATABASE_URL`:** `ConfigError: DATABASE_URL is required (see services/api/.env.example)`, con la traza de uvicorn al cargar la factory. Es el mismo comportamiento que ya tenía la falta de `JWT_SECRET_KEY` y no muestra ningún secreto.
- **Validación:**
  - `unittest`: 348 OK (312 + 36).
  - `uv run --no-sync python -m pytest`: 551 OK (515 + 36).

---

## 2026-10-17 — Hito 5 (inventario con SQLModel y Supabase), F1: rama, CONTEXT y dependencias

**Estado: hecho y validado, sin comitear** (el usuario revisa cada fase antes del commit), en `feature/inventory-orm`, creada desde `main` en `ef1e083` (merge de la PR #20). Primera fase del plan aprobado por el usuario (F1, F2, F3a, F3b, F4 y F5). Todavía no hay código de inventario.

- **CONTEXT del hito versionado:** `docs/context-nexova-gestion-inventario-hito-5.md`, sin cambios de contenido (solo finales de línea a LF).
- **Dependencias directas nuevas (autorizadas por el enunciado):**
  - `sqlmodel>=0.0.48,<0.0.49` (instalada 0.0.48);
  - `psycopg2-binary>=2.9.13,<2.10` (instalada 2.9.13; tiene wheel `cp314-win_amd64`).
  - Única transitiva nueva: SQLAlchemy 2.1.5.
  - Añadidas con `uv add --no-sync` e instaladas con `uv run`, que sincroniza de forma inexacta.
  - `pip list` antes y después: solo aparecen esos tres paquetes; `nexova-shared` y `nexova-incident-analyzer` siguen instalados.
- **`.env.example`:** `DATABASE_URL=` vacía, con un comentario sobre el Transaction pooler (puerto 6543) y los esquemas aceptados. Será obligatoria a partir de F2. `.env` no se ha tocado.
- **Conexión real:** un `SELECT 1` contra Supabase con un script fuera del repo responde `ok`. Solo imprime `ok` o la clase del error.
- **Hallazgo para F2:** SQLAlchemy 2.1 resuelve `postgresql://` con psycopg (v3), que no está instalado; con la URL tal cual, `create_engine` falla con `ModuleNotFoundError`. El motor tendrá que fijar `postgresql+psycopg2` al construirse.
- **Validación:**
  - `unittest`: 312 OK.
  - `uv run pytest`: 515 OK, con 1 aviso de Starlette sobre httpx que no viene de las dependencias nuevas.
  - Lanzada como `uv run --no-sync python -m pytest`, porque el Control de aplicaciones de Windows bloquea hoy `.venv/Scripts/pytest.exe` (os error 4551). Ese ejecutable es del 2026-10-10 y F1 no lo ha cambiado.

---

## 2026-10-13 — Memory-bank: AUTH-088 integrada en `main`

**Estado: hecho** en `chore/memory-bank-auth088-merged`, creada desde `main` en `a56e346`. Solo documentación; sin impacto técnico.

- **Hechos comprobados con git** (`git fetch` + `git log --merges main`): `main` está en `a56e346`, el merge de la PR #19 (`feature/auth-088-test-suite`, 2026-10-13). Antes, la PR #18 (`feature/error-handling-audit`, merge `843ae26`, 2026-10-10) y la PR #17 (`feature/centralized-incident-manager`, merge `6dfa013`, 2026-10-08).
- **`progress.md`:** la entrada de cierre de AUTH-088 decía «sin subir»; corregida.
- **`techContext.md`:** el estado verificado de `origin/main` pasa de `6dfa013` a `a56e346`, con las PRs #18 y #19.
- **`AGENTS.md` §4:** el gestor centralizado de incidencias deja de figurar «pendiente de PR».

---

## 2026-10-13 — AUTH-088: cierre de la rama (verificación final)

**Estado: rama `feature/auth-088-test-suite` completa y verificada.** ~~Sin subir; push y PR los hace el usuario.~~ *Corregido el 2026-10-13: integrada en `main` con la PR #19 (merge `a56e346`).* 13 commits sobre `main` (`843ae26`): F1 a F8, tres `fix` (`65cfb36` tope de minutos, `988ff96` byte NUL, `1ddaaf8` título con emojis) y los `docs`.

**Verificación final** (HEAD frente a `main`; los totales de `main` se midieron sobre una copia extraída con `git archive` y los `node_modules` del repo enlazados con una unión de directorio, ya eliminada):

| Suite | `main` (`843ae26`) | HEAD |
|---|---|---|
| `services/api`: `uv run pytest` | — (sin pytest) | 515 OK |
| `services/api`: `unittest` (`AGENTS.md`) | 312 OK | 312 OK |
| Cobertura global de `app/` | 97 % | 98 % |
| Cobertura de auth (`--fail-under=70`) | 96 % | 99 % |
| Cobertura de los módulos de API-042 | 99 % | 99 % |
| `uis/backoffice`: `node:test` | 344 OK | 344 OK |
| `uis/backoffice`: `npm run test:jest` | — (sin Jest) | 161 OK |
| `uis/backoffice`: `tsc`, `lint` y `build` | no se reejecutaron | limpios |
| `packages/shared` | 81 OK (sin cambios en la rama) | 81 OK |
| `packages/incident-analyzer` | 121 OK, 7 omitidos (sin cambios) | 121 OK, 7 omitidos |
| `src/`: `npm run check` | 97 OK (sin cambios) | 97 OK |

- **`git diff main..HEAD --stat`:** idéntico con y sin `--ignore-cr-at-eol` (44 archivos).
- **Sin archivos que no deban subir:** ni `.vscode/`, ni `.env` (solo `.env.example`), ni `.coverage`, `coverage/`, `htmlcov/` o bases de datos.
- **Dependencias directas nuevas:** solo pytest, pytest-cov y httpx (grupo `dev` de uv), y jest, ts-jest y @types/jest. El resto de `uv.lock` y `package-lock.json` son transitivas; no se elimina ni cambia ninguna existente.
- **Huella de `services/api/data/*.json`:** idéntica.
- **Relectura de `TESTING.md` como evaluador:**
  - quitada la jerga «RP1»/«RP3» de §4;
  - el tiempo de la suite completa pasa a «~1–2 min» (hoy, 109 s);
  - aclarado que los 112 tests de Jest de auth son parte de los 161;
  - el título y las filas mencionan también los extras.
  - Enlaces comprobados con un script.
- **Incidencias de la verificación:** un worktree de `main` en el scratchpad falló al poblarse (probablemente por la longitud de la ruta en Windows). No quedó registrado y el repo no se vio afectado. Se usó `git archive` en su lugar.

---

## 2026-10-13 — AUTH-088, F8 (extra FE-019): utilidades del frontend con Jest (y el bug del título con emojis)

**Estado: hecho, validado y comiteado** en `feature/auth-088-test-suite`: el fix en `1ddaaf8` (`fix(backoffice)`, con sus tests), los tests en `1c9ed4a` (`test(backoffice)`) y la documentación en el commit `docs` siguiente.

**Qué se hizo:**
- **`uis/backoffice/__tests__/utils/`:** 49 tests en 4 archivos. `node:test` ya cubría los casos generales, así que aquí van los límites que faltaban:
  - `supplier-renewal.test.ts` (`daysUntil`, `renewalInfo`): hoy, día 59 (29-02-2028), día 60 y día 61 alrededor de un año bisiesto; la hora del día y los cambios de horario de 2026 no alteran la cuenta; 2026-02-30, 2027-02-29, 2026-2-3, mes 13 o 0, 2026-04-31 y espacios → `null`; `null` y fecha pasada;
  - `suppliers.service.test.ts` (`parseRate`, `validateSupplierForm`): coma decimal; `0,00`, separador de miles, signos, símbolo de moneda, `Infinity` y `NaN` → `null`; las fechas y el email opcionales no se validan en el cliente;
  - `incident-manager.service.test.ts` (`countCharacters`, `validateIncidentForm`, `messageForApiError`): el límite del título (los tests llegaron con el fix), la descripción en blanco, la sede obligatoria para cualquier origen y los textos por código;
  - `api-error-body.test.ts` (`normalizeApiErrorBody`): un `detail` de texto se conserva y uno estructurado se descarta.
- **`jest.config.mjs`:** `collectCoverageFrom` añade `lib/supplier-renewal.ts`, `services/suppliers.service.ts` y `services/incident-manager.service.ts`.
- **README del backoffice:** el párrafo de Jest incluye las utilidades.

**Bug encontrado y corregido** (entrada en `TESTING.md` §5, tercera columna):
- **Qué lo destapó:** un caso límite de esta batería: ¿el cliente cuenta los caracteres del título como la API?
- **Síntoma:** con 61 emojis, el formulario de alta de incidencias decía «no puede superar los 120 caracteres» y el contador marcaba 122 / 120. La API acepta ese título (61 caracteres).
- **Causa:** `validateIncidentForm` y el contador de `incident-form.tsx` medían con `.length` (unidades UTF-16: un emoji vale 2), y la API con `len()` de Python (caracteres).
- **Corrección (opción a del usuario):** `countCharacters` (`[...value].length`) en `services/incident-manager.service.ts`, usada por la validación y por el contador.
- **Mismo patrón en el resto del backoffice:** revisado, no hay más. Era el único límite de longitud que comprobaba el cliente; el perfil (200), el email (254) y la contraseña (8 y 72 bytes) solo los valida la API.
- **Commit:** `1ddaaf8`.
- **Tests:** `61 emojis are accepted` y el resto del límite del título (120 / 121 ASCII, 60, 120 y 121 emojis).

**Validación:**
- `npm run test:jest`: 161 OK (112 de auth y 49 de utilidades) en ~1 s.
- `tsc`, `lint` y `build` limpios; `node:test`: 344 de 344 OK.
- **Cobertura (líneas):**
  - `supplier-renewal.ts`: 100 %;
  - `suppliers.service.ts`: 35,2 %;
  - `incident-manager.service.ts`: 44,3 %;
  - `normalizers.ts`: 58,5 %.
  - Las cinco funciones probadas quedan al 100 %; lo no cubierto son los `build*Payload`, las clases de error y la parte HTTP, que cubre `node:test`.
- **Mutaciones**, todas detectadas y deshechas, con `git diff` de `lib/`, `services/` y `hooks/` vacío:
  - ventana sin el día 60;
  - sin la comprobación de calendario (6 tests);
  - `parseRate` sin coma decimal (3);
  - `status`/`invalid_choice` con el texto genérico;
  - descripción sin recortar;
  - volver a `.length` (3).

---

## 2026-10-13 — AUTH-088, F7 (extra API-042): proveedores y gestor de incidencias con pytest

**Estado: hecho, validado y comiteado** en `feature/auth-088-test-suite`: los tests en `63ef418` (`test(api)`) y la documentación en el commit `docs` siguiente.

**Qué se hizo:**
- **Antes de escribir:** revisados `test_suppliers_api.py` y `test_incident_manager_*.py`. Cubrían el contrato HTTP y el repositorio del gestor por dentro (transiciones, filtros, orden con fechas distintas y seed). Esta batería fija lo que solo se probaba por HTTP o no se probaba:
  - las funciones de ruta de los dos grupos;
  - `updated_at` con el reloj controlado;
  - el desempate por `id` con la misma fecha;
  - una transición inválida deja el archivo intacto byte a byte.
- **`conftest.py`:** fixtures `supplier_repo` e `incident_repo` (base temporal y reloj del test); el docstring menciona las dos baterías.
- **`test_suppliers_logic.py`:** 30 tests:
  - alta con id y hora;
  - límites de tarifa y fecha (0,01, entera, 29-02-2028, 2026-02-29, 2026-3-1);
  - reglas del CONTEXT (moneda/país, enumeraciones, tarifa de texto o infinita, `id`/`updated_at` del cliente);
  - filtros (categoría entre varias, AND, vacío);
  - 404 en lectura, tarifa, estado y borrado sin escribir;
  - la tarifa registra la hora y el estado no;
  - borrado y doble borrado;
  - seed idempotente por `name` sin pisar.
- **`test_incident_manager_logic.py`:** 30 tests:
  - alta `open` con texto recortado y fechas del reloj;
  - título de 120 / 121;
  - 400 sin escribir;
  - filtros AND (cada incidencia descartada difiere en un solo campo);
  - orden y desempate por `id`;
  - filtro fuera del vocabulario → 400;
  - resumen con datos y vacío;
  - `get` y 404;
  - transición válida (solo `status` y `updated_at`), `open → discarded` y `discarded` final;
  - transición inválida sin tocar el archivo;
  - 404 y cuerpo mal formado;
  - seed idempotente por clave de origen, con la fecha y el estado del histórico.

**Hallazgo documentado, no corregido** (decisión del usuario): TinyDB reutiliza el `id` del último proveedor borrado (se borra el 2, se crea otro y recibe el 2). Ningún documento lo prohíbe (D-SUP-4, D-AUTH-2). Está en `TESTING.md` §7, sin test que lo fije.

**Validación:**
- `uv run pytest`: 515 OK (455 + 60). Huella de `data/` idéntica.
- Cobertura de `app/routes/suppliers.py`, `app/database.py`, `app/models.py` y `app/modules/incident_manager/`: **92,6 %** con la batería sola (menos de 1 s) y **99,0 %** con la suite completa.
- Global de `app/`: 98 %; auth: 99 %.
- **Mutaciones**, todas detectadas y deshechas, con `git diff -- app` vacío:
  - el estado del proveedor toca `updated_at`;
  - la tarifa no registra `updated_at`;
  - sin el filtro de categoría;
  - el seed no comprueba el `name`;
  - aceptar una transición inválida;
  - invertir el orden;
  - sin el filtro de origen, de sede o de categoría del gestor;
  - el seed del gestor no comprueba la clave.
  - La del filtro de origen sobrevivió a la primera versión del test de filtros y se reforzó.
- **`TESTING.md`:** §11 (este extra), §12 (FE-019), el tercer bug en §5, el riesgo del id en §7 y los totales de §9.

---

## 2026-10-12 — AUTH-088, F6: Jest para la lógica TypeScript de autenticación (`uis/backoffice`)

**Estado: hecho, validado y comiteado** en `feature/auth-088-test-suite`, después de F5 (`f482e02`). No ha destapado ningún bug.

**Dependencias** (autorizadas por el ticket; solo `devDependencies`):
- **Versiones:** `jest ^30.5.2`, `ts-jest ^29.4.14` y `@types/jest ^30.0.0`.
- **Compatibilidad comprobada con `npm view`:** ts-jest 29.4.14 declara `jest ^29 || ^30` y `typescript >=4.3 <7`; el TypeScript instalado es la 5.9.3. @types/jest 30 corresponde a Jest 30.
- **`package-lock.json`:** solo altas (243 paquetes). Ninguna versión existente cambia ni se elimina; solo cambian las `devDependencies` de la entrada raíz. Con el algoritmo `histogram`, el diff son 3578 inserciones y 0 borrados; el diff por defecto de git aparenta 2306 borrados por cómo alinea.
- **`@parcel/watcher` 2.6.0:** transitiva de `jest-haste-map`. npm no ejecutó su install script (política `allowScripts`) y no se ha aprobado; Jest funciona sin él.

**Qué se hizo:**
- **`jest.config.mjs`:** entorno `node`; `roots` y `testMatch` limitados a `__tests__/**/*.test.ts`, así que `tests/*.test.mjs` sigue con `node:test`; `@/` → `<rootDir>/`; ts-jest en CommonJS; `.next/` ignorado; `collectCoverageFrom` con los cinco archivos de auth.
- **`package.json`:** script `"test:jest": "jest --coverage"`.
- **`coverage/`:** `/coverage` ya estaba en el `.gitignore` del backoffice (plantilla de Next). Se añade `coverage/**` a los ignorados de `eslint.config.mjs`, porque si no ESLint analiza el informe que genera Jest (daba un aviso).
- **`__tests__/support/`:**
  - `fake-browser.ts`: Storage en memoria y `window` con `addEventListener` y `removeEventListener`;
  - `fake-api-client.ts`: cumple la interfaz `ApiClient`.
  - `__tests__/` queda preparado para las utilidades de FE-019.
- **`__tests__/auth/`:** 112 tests en 5 archivos:
  - `auth-token`: con `jest.isolateModules` y `jest.requireActual` por el estado del módulo;
  - `auth-routes`;
  - `auth.service`: los `validate*`, los `build*`, `buildLoginForm` y `createAuthService` con el cliente falso;
  - `normalizers` (parte de auth);
  - `use-auth-session`: reducer, estado derivado, textos y, además de lo pedido, `createAuthSessionController`.
- **Añadidos durante la fase** (para cubrir lógica de auth que la cobertura dejó ver): `getCurrentUser` (401 → `session_expired`), `updateProfile`, `requestPasswordReset`, el 422 del registro por campo y `registered_login_failed`.

**Verificado:**
- `npx jest --coverage` y `npm run test:jest`: 112 OK y código de salida 0.
- Cobertura de líneas (Jest):
  - `auth-routes` y `auth-token`: 100 %;
  - `auth.service`: 93,4 %;
  - `use-auth-session`: 80,3 % (sin el hook de React);
  - `normalizers`: 58,5 % (lo no cubierto no es de auth);
  - total de los cinco archivos: 80,2 %.
- `npx tsc --noEmit`, `npm run lint` y `npm run build`: limpios.
- `node:test` con el comando de `AGENTS.md`: 344 de 344 OK.
- **Mutaciones**, todas detectadas y deshechas, con `git diff -- uis/backoffice/lib uis/backoffice/services uis/backoffice/hooks` vacío:
  - `readAuthToken` sin `trim` → falla `a token made only of spaces…`;
  - `/reset-password` tratada como solo pública → falla `/reset-password renders with session authenticated…`;
  - guardar el token aunque la normalización falle → fallan 2 tests del login;
  - `normalizeAccessToken` acepta un `expires_in` no entero → fallan 3 tests.
- **Sin lógica de tokens ni de hash en TypeScript:** buscados `atob`, `jwt-decode`, `bcrypt`, `crypto.subtle` y `createHash` en el código de producción, sin coincidencias. Documentado en `TESTING.md` §10.

**Documentación:**
- `TESTING.md` §10 (Jest);
- `uis/backoffice/README.md` («Validación»), con el enlace a `TESTING.md`;
- `uis/backoffice/CLAUDE.md`: la excepción de dependencias y dónde va cada tipo de test;
- `AGENTS.md` §4: `npm run test:jest` en la fila del backoffice;
- `techContext.md`: las dependencias del backoffice.

---

## 2026-10-12 — AUTH-088, F5: `services/api/TESTING.md` y documentación

**Estado: hecho, validado y comiteado** en `feature/auth-088-test-suite`, después de F4 (`9a47153`). A petición del usuario, §6 de `TESTING.md` explica también cómo se usó la IA (propuso el plan y los casos; el desarrollador decidió qué entraba y revisó cada test y corrección). Antes de F5, el test de concurrencia de F4 se ajustó: `join(timeout=10)`, `assert not thread.is_alive()` e hilos `daemon` (va en el commit de F4).

**Qué se hizo:**
- **`services/api/TESTING.md` (nuevo, breve):**
  - qué cubre y por qué;
  - cómo ejecutar, con los comandos comprobados en PowerShell (la cobertura de auth en un solo comando con `--cov=app.auth … --cov-fail-under=70`, más la alternativa `uv run python -m coverage report …`), la nota sobre `coverage.exe` y el aviso de `uv sync` con la reinstalación;
  - huecos marcados para Jest (F6) y para los extras (F7 y F8);
  - el plan por endpoint (12 más JWT y configuración: feliz, límite, fallo y archivo);
  - por qué estos casos y la tabla de mutaciones;
  - los dos bugs (`65cfb36` y `988ff96`);
  - los casos de la IA, aceptados y solo documentados;
  - los riesgos M-1…M-3, L-1…L-6 y el H-1 residual;
  - los límites de la batería y los resultados.
- **Enlaces a `TESTING.md`:** desde `AGENTS.md` §4 (fila de `services/api`, con `uv run pytest` como alternativa válida y «no usar `uv sync`») y desde `services/api/README.md` («Tests»). El README aclara además que el comando `unittest` no recoge la batería de AUTH-088. El README raíz no se toca (decisión del usuario).
- **Byte NUL documentado:** en la línea de contraseñas de `services/api/README.md` y en la fila «Validación de entrada» de `docs/auth-password-reset.md` §11.
- **`docs/auth-password-reset.md` §14:** L-4, resuelto por A1 (`24f0e0d`).
- **`techContext.md`:** la fila de la API ya no dice que pytest «ejecuta la misma suite».

**Verificado durante F5:**
- **Comandos literales en PowerShell desde `services/api`:**
  - `uv run pytest` → 455 OK en ~51 s;
  - `uv run pytest --cov` → cobertura global de `app/` del 98 %;
  - la cobertura de auth en un solo comando → 98,93 % («Required test coverage of 70% reached»);
  - `uv run python -m coverage report --include=… --fail-under=70` → 99 % y código de salida 0;
  - solo la batería nueva con la cobertura de auth → 143 OK, 85,63 %, en ~10 s;
  - el comando `unittest` de `AGENTS.md` desde la raíz → 312 OK en ~41 s.
- **`coverage.exe`:** hoy arranca (en F1 lo bloqueó el Control de aplicaciones); la nota lo dice así.
- **Detección de mutaciones de F2:** vueltas a ejecutar para saber qué test detecta cada una:
  - `*60` → `*1`: 8 casos de 4 tests;
  - sin `require_exp`: el caso `[sin exp]`;
  - aceptar HS512: el caso `[HS512 …]`;
  - sin el burn de la ruta: 4 casos del test del email mal formado;
  - sin el tope: los 2 casos del test estricto.
  - `app/` queda intacto.
- **Comportamientos de los casos solo documentados:**
  - una contraseña de 8 espacios se acepta;
  - un email Unicode se acepta y se pasa a minúsculas;
  - un `iat` en el futuro se acepta, pero un `nbf` en el futuro lo rechaza python-jose;
  - un perfil `"   "` se guarda como `""`.
- **Enlaces relativos y anclas** de `TESTING.md`, `AGENTS.md`, `services/api/README.md` y `docs/auth-password-reset.md`: todos resuelven (script de comprobación).

**Pendiente para F6:**
- el enlace a `TESTING.md` desde `uis/backoffice/README.md`, cuando exista la sección de Jest;
- rellenar el hueco de Jest en `TESTING.md`;
- `coverage/` en el `.gitignore` del backoffice;
- la excepción de dependencias en `uis/backoffice/CLAUDE.md`.

---

## 2026-10-12 — AUTH-088, F4: tests de recuperación y cambio de contraseña

**Estado: hecho, validado y comiteado** en `feature/auth-088-test-suite`, después de F3 (`d7565a6`). No ha destapado ningún bug.

**Qué se hizo** (sin TestClient: rutas, servicio y repositorio llamados directamente):
- **`conftest.py`:**
  - `fake_request()`: un `Request` mínimo con IP de TEST-NET-3, para la auditoría;
  - `read_table`: lee una tabla de la base temporal;
  - `bcrypt_verify_calls`: el espía de bcrypt, movido aquí desde `test_login.py` porque ahora lo usan dos archivos.
- **`test_forgot_password.py`:** 8 tests (FP1–FP4). La ruta se llama con un `BackgroundTasks` real y se inspeccionan las tareas encoladas:
  - email registrado: en la base solo el SHA-256 (el token en claro no aparece en el archivo), `expires_at` según el reloj, auditoría `reset_requested` con IP, y la tarea encolada envía el enlace con ese token;
  - email desconocido o usuario inactivo: la misma respuesta, sin fila de token, sin tarea y con la auditoría `unknown_email` sin `user_id`;
  - email normalizado; un único pendiente tras dos peticiones (el primero da `UNKNOWN`); purga de los caducados de otros usuarios;
  - el sender que falla y `DisabledEmailSender`: no lanzan, y el log de `nexova.api` es exactamente «… could not be delivered: <Clase>», sin traza, sin email y sin token (con `tests/support.capture_logs`).
- **`test_reset_password.py`:** 14 tests (RP1–RP4 y la concurrencia):
  - la contraseña nueva vale y la antigua no; `used_at` y la auditoría `reset_completed`;
  - 1 s antes de `expires_at` es válido; justo en `expires_at`, `EXPIRED`;
  - tras un reset correcto, los demás pendientes dejan de valer. El segundo pendiente se fabrica a mano, porque hoy `replace_reset_token` deja uno solo: es defensa en profundidad;
  - usado, caducado, anulado por un enlace nuevo o por change-password, usuario borrado o inactivo, y desconocido → el mismo `InvalidResetTokenError`, sin cambiar el usuario, y la auditoría `reset_rejected` con el motivo real. El `user_id` es `None` cuando la fila del token ya no existe;
  - token `""` o de 513 caracteres → validación (512 se acepta).
- **Concurrencia (caso de la IA):** dos `consume_reset_token` con el mismo token, `threading.Barrier(2)` y `sys.setswitchinterval(1e-6)`, sin sleeps, 25 rondas: siempre `[used, valid]`. Los errores de los hilos se anotan en el resultado para que el assert diga qué pasó. Determinista: 20 de 20 ejecuciones en verde.
  - **Bloqueos:** `join(timeout=10)` y `assert not thread.is_alive()` («posible bloqueo en consume_reset_token»), con los hilos `daemon`. Comprobado con un deadlock provocado (adquirir dos veces el lock no reentrante): sin `daemon`, el test fallaba pero pytest no terminaba nunca; con `daemon`, falla a los 10 s y el proceso termina.
  - **Medido con un script desechable** (subclase sin lock, 200 rondas): con lock, 200/200 correctas. Sin lock y con `switchinterval` 1e-6, ninguna ronda correcta: 31 con dos `VALID`, 167 con el archivo TinyDB corrupto (503) y 2 mixtas. Con el intervalo por defecto, 197 corruptas y 2 con doble `VALID`.
  - Conclusión: el lock evita también que la base se corrompa, no solo el doble uso.
- **`test_change_password.py`:** 6 tests (CP1–CP3):
  - cambia la contraseña, la auditoría `password_changed` lleva la IP y se purgan los enlaces de reset;
  - la nueva igual a la actual se acepta (D-PWD-10);
  - una actual de más de 72 bytes, o con NUL (cierra el caso del fix `988ff96`), es incorrecta sin llegar a bcrypt;
  - una actual incorrecta da 400 (no 401), sin cambios y con la auditoría `password_change_rejected`;
  - usuario borrado tras autenticarse → `UserNotFoundError`, sin recrearlo ni auditar el cambio.

**Validación:**
- Suite completa: de 427 a **455 OK**. Los tres archivos nuevos solos: 28 OK.
- `uv run pytest --durations=10` antes de F4: ~1:15 en total. Los 10 tests más lentos son de la suite antigua (TestClient y bcrypt), ninguno de F2/F3; los 5:54 de una ejecución de F3 fueron carga de la máquina.
- Cobertura de auth: **86 %** solo con F2+F3+F4 y **99 %** con la suite completa. Sin cubrir con los nuevos: el cableado de FastAPI en `dependencies.py`, el sender de Resend y `create-admin`, que cubre la suite antigua.
- Mutaciones, todas detectadas y deshechas, con `app/` intacto según `git diff`:
  - `<=` → `<` en la caducidad de `consume_reset_token` → falla el test de `expires_at` exacto;
  - no invalidar los pendientes al pedir un enlace nuevo → fallan el del pendiente único y el de «anulado por un enlace nuevo»;
  - no purgar los resets en change-password → fallan el CP1 y el de «anulado por change-password»;
  - no marcar `used_at` → fallan 4 tests: RP1, la purga, «ya usado» y la concurrencia;
  - quitar el lock de `consume` → falla la concurrencia 10 de 10 veces (8 por archivo corrupto, 1 mixta y 1 por dos `VALID`);
  - que forgot-password encole también para desconocidos → fallan los 2 casos de FP2;
  - extra: el reset no purga los otros pendientes → falla el test de la purga.
- `services/api/data/*.json`: huella idéntica.

---

## 2026-10-12 — AUTH-088, F3: tests de registro, usuarios y perfiles (y el bug del byte NUL)

**Estado: hecho, validado y comiteado** en `feature/auth-088-test-suite`: el fix en `988ff96` (`fix(api)`) y los tests en el commit siguiente (`test(api)`).

**Qué se hizo** (todo sin TestClient: rutas, servicio, repositorio y modelos llamados directamente, con las fixtures de `conftest.py`):
- **`test_register.py`:** 27 tests (R1–R9 y el NUL):
  - el usuario se crea con `role=user`, activo, con hash verificable y con perfil, y la respuesta va sin hash;
  - el email se guarda normalizado; el duplicado exacto, en mayúsculas o con espacios da 409 y no crea un segundo perfil;
  - contraseña de 7/8 caracteres y de 72/73 bytes; multibyte (ñ×36 OK, ñ×37 error, 😀×18 OK, 😀×19 error, ñ×7 error);
  - email o contraseña vacíos; campos prohibidos (`role`, incluso `user`; `hashed_password`, `id`, `is_active`, `user_id`) → `extra_forbidden`;
  - email de 254/255 caracteres; perfil recortado y de 200/201 caracteres;
  - el NUL en cada modelo de contraseña nueva (`UserCreate`, `UserUpdate`, `ResetPasswordRequest`, `ChangePasswordRequest`) → error de validación y bcrypt no se llama (espía de `hash` y `verify`).
- **`test_users.py`:** 25 tests (U1–U11):
  - el admin lista sin hashes; `require_admin` con `user` y `manager` → 403;
  - GET: uno mismo y el admin OK; el admin sobre un inexistente → 404; un no-admin sobre otro → 403, exista o no;
  - PUT: email propio normalizado; cuerpo vacío, `password: null` y `role: null` sin cambios y sin 403; el email propio en mayúsculas no da 409; el email de otro (también en mayúsculas) → 409 sin cambios;
  - H-1: `password` de `user`/`manager` → 403 y no se aplica nada (tampoco el email de la misma petición); `role` de un no-admin → 403; con `role` y `password` a la vez gana la regla del rol;
  - el admin fija la contraseña y el rol de otro; el admin sobre un inexistente (vacío o con email) → 404 y no lo crea;
  - DELETE propio: borra el perfil y el token antiguo da 401; un no-admin sobre otro → 403; el admin sobre un inexistente y el doble borrado → 404.
- **`test_profiles.py`:** 10 tests (P1–P4): GET y PUT parcial; `null` borra, el cuerpo vacío no cambia nada, `strip` y 200/201; campos extra (`user_id`, `id`, `email`) → `extra_forbidden`; un usuario sin perfil → `ProfileNotFoundError` en GET y PUT, y el PUT no lo crea.
- **`test_login.py`** (en el commit del fix): un NUL con email existente o desconocido → el mismo `InvalidCredentialsError`, sin llegar a bcrypt (espía con control positivo).

**Bug encontrado y corregido** (la entrada para «Bugs encontrados» de `services/api/TESTING.md`, F5):
- **Qué lo destapó:** el caso propuesto por la IA y aprobado por el usuario «byte NUL en la contraseña: ¿error de validación o excepción de bcrypt que sería un 500?». Se comprobó llamando a la lógica y con un diagnóstico HTTP desechable sobre una TinyDB temporal, fuera del repo.
- **Síntoma:** `500 internal_error` en `POST /users`, en `POST /auth/login` (con el email existente o desconocido), en `POST /auth/reset-password`, en `POST /auth/change-password` (la contraseña nueva y la actual) y en el `PUT /users/{id}` del admin con `password` (este último, por el mismo `hash_password`; no se probó por HTTP).
- **Causa:** bcrypt no admite el byte NUL y passlib lanza `PasswordValueError` al hashear o comparar. Ni `_check_password` (`app/auth/models.py`) ni `verify_password` (`app/auth/security.py`) lo tenían en cuenta; `burn_password_check` pasa por `verify_password` y también lanzaba la excepción.
- **Corrección (opción a del usuario):** se trata igual que el límite de 72 bytes.
  - `_check_password` rechaza el NUL: 422 en las cuatro entradas de contraseña nueva.
  - `verify_password` devuelve `False` sin llamar a bcrypt, porque ninguna contraseña registrada puede contenerlo.
  - `burn_password_check` no lleva una comprobación propia: hereda la de `verify_password`, igual que con los 72 bytes. Así, el login con un NUL da el mismo 401 exista o no el email, y por los dos caminos sin bcrypt. Una contraseña actual con NUL da el 400 `incorrect_password`.
  - Una frase en `SPECS.md` D-AUTH-7.
  - Verificado al leer el código: las cuatro contraseñas nuevas usan `Password` (`_check_password`). `ChangePasswordRequest.current_password` no lo usa, y es correcto que no: se compara, no se hashea; lo cubre `verify_password`.
- **Commit:** `988ff96` (`fix(api)`).
- **Tests que lo fijan:**
  - `test_login.py::test_password_with_nul_byte_fails_like_bad_credentials_without_reaching_bcrypt`;
  - `test_register.py::test_new_password_with_nul_byte_is_rejected_before_reaching_bcrypt` (4 casos);
  - el de la contraseña actual queda para `test_change_password.py` (F4).

**Validación:**
- Suite completa (`uv run pytest`): de 365 (364 de F2 + el test de login del fix) a **427 OK**. Los tres archivos nuevos solos: 62 OK en unos 4 s. El comando `unittest` de `AGENTS.md`: 312 OK (no descubre los tests de estilo pytest).
- Cobertura del módulo de auth (`app/auth/*` y `app/routes/{auth,users,profiles}.py`): **71 %** solo con los tests de F2+F3; **98 %** con la suite completa.
- Mutaciones, todas detectadas y deshechas, con `app/` intacto según `git diff`:
  - quitar H-1 en `update_user` → fallan los 2 casos (user/manager) del test de H-1;
  - invertir el orden role/password → falla `test_role_rule_is_checked_before_the_password_rule`;
  - quitar `normalize_email` → fallan 8 tests de registro y usuarios;
  - 72 bytes → 72 caracteres → fallan ñ×37 y 😀×19;
  - no borrar el perfil en `delete_user` → falla el test del borrado propio;
  - quitar el NUL de `_check_password` → fallan los 4 casos de los modelos;
  - quitar el NUL de `verify_password`, o un burn que llame a bcrypt directamente → falla el test de login con NUL.
- `services/api/data/*.json`: huella idéntica.

**Pendiente:** `services/api/README.md` (línea de contraseñas) y la fila «Validación de entrada» de `docs/auth-password-reset.md` §11 todavía no mencionan el NUL; se revisan en F5 junto con `TESTING.md`.

---

## 2026-10-11 — AUTH-088, F2: tests de token, configuración y login (y el bug que destaparon)

**Estado: hecho, validado y comiteado** en `feature/auth-088-test-suite`: el fix en `65cfb36` (`fix(api)`) y los tests en el commit siguiente (`test(api)`), después de F1 (`42c4529`).

**Qué se hizo:**
- **`services/api/tests/conftest.py`:** fixtures de estilo pytest:
  - `clock` (fijo y avanzable), `settings` (bases en `tmp_path` y clave generada), `auth_repo`, `service` y `fake_sender`;
  - `make_user`, que reutiliza un hash bcrypt calculado una vez por sesión, y `drop_profile`;
  - la fixture `autouse` de sesión que compara la huella SHA-256 de `services/api/data/*.json` antes y después. Se aplica también a los tests `unittest`.
- **`test_token.py`:** 41 tests (incluido el tope técnico de minutos, ver el bug abajo) sobre la lógica de `security`, `get_current_user`, `read_current_user` y `Settings`, sin HTTP:
  - `exp == iat + N*60` para N = 1, 30 y 1440 (la regresión del ticket), y token justo antes y justo después de caducar (calculado desde la configuración, no desde `expires_in_seconds`);
  - otra clave, HS512, `alg: none`, sin `sub`, `sub` vacío o numérico, sin `exp`, y tokens malformados;
  - usuario borrado o inactivo, y sin token;
  - `/auth/me` con y sin perfil;
  - configuración: minutos ausentes, 0, −1, `abc`, `1.5`, `1e3` y `"   "`; clave de 31 y 32 caracteres y medida tras el `strip`.
- **`test_login.py`:** 11 tests; la ruta `login` se llama directamente con `OAuth2PasswordRequestForm(username=…, password=…)` construido a mano (verificado):
  - el token y `expires_in` correctos; el email normalizado;
  - el mismo error para contraseña incorrecta y email desconocido;
  - email mal formado → 401 y burn (espía con monkeypatch);
  - más de 72 bytes nunca llegan a bcrypt (espía de `bcrypt.verify` con un control positivo);
  - usuario inactivo y contraseña vacía.

**Bug encontrado y corregido.** Es la entrada para la sección «Bugs encontrados» de `services/api/TESTING.md` (F5):
- **Qué lo destapó:** un caso propuesto por la IA y aprobado por el usuario. La primera versión del test, `test_absurd_expiration_is_rejected_at_startup_not_at_every_login`, aceptaba las dos salidas válidas (rechazo al arrancar o token emitido) y falló.
- **Síntoma:** con `ACCESS_TOKEN_EXPIRE_MINUTES = 10**10`, la API arrancaba con normalidad, pero cada login respondía 500 (`OverflowError: date value out of range` en `create_access_token`, `app/auth/security.py`). 10**9 todavía funcionaba.
- **Causa:** `Settings.__post_init__` solo rechazaba 0 y negativos. `iat + timedelta(minutes)` se sale del rango de `datetime` (año 9999).
- **Corrección (decisión del usuario, opción b):** `MAX_ACCESS_TOKEN_EXPIRE_MINUTES = 525_600` (1 año) en `app/core/config.py`, con `ConfigError` «must be between 1 and 525600», también por `from_env`. Es un **tope técnico, no una política de sesión**: ningún documento fija la duración máxima, que queda pendiente del CTO. Documentado en `SPECS.md` (§7) y en `.env.example`. Ningún test existente usaba más de 45 minutos.
- **Commit:** `65cfb36` (`fix(api)`).
- **Tests que lo fijan ahora (estrictos):**
  - `test_expiration_at_the_technical_cap_is_accepted_and_signs_tokens` (525600 se acepta y firma);
  - `test_expiration_beyond_the_technical_cap_is_rejected_at_startup` (525601 y 10**10 → `ConfigError` al construir `Settings` y por `from_env`).

**Validación:**
- Suite completa: de 312 a **364 OK**. Los nuevos solos: **52 OK** en unos 2 s.
- Cobertura del módulo de auth con los tests nuevos solos: 48 % (F3 y F4 cubren el resto).
- Mutaciones, todas detectadas y deshechas, con `app/` intacto según `git diff`: `*60 → *3600`, `*60 → *1`, quitar `require_exp`, quitar el burn de la ruta, quitar el burn de `authenticate`, aceptar HS512 y quitar el tope de minutos.
- `services/api/data/*.json`: huella idéntica.

---

## 2026-10-10 — AUTH-088, F1: pytest y pytest-cov en `services/api`

**Estado: hecho y validado, sin comitear** (el usuario revisa cada fase antes del commit), en `feature/auth-088-test-suite`, que sale de `main` en `843ae26` (merge de la PR #18). Primera de las fases del plan de AUTH-088 (batería de pruebas unitarias de la API de autenticación), aprobado por el usuario; las siguientes (F2–F8) escriben los tests, `services/api/TESTING.md` y Jest en el backoffice.

**Qué se hizo:**
- **`pyproject.toml`:**
  - `uv add --dev --no-sync --bounds minor pytest pytest-cov httpx` → `[dependency-groups] dev`, con los rangos ajustados a mano al estilo del proyecto: `httpx>=0.28,<0.29`, `pytest>=9.1,<9.2` y `pytest-cov>=7.1,<7.2` (`--bounds minor` dejaba httpx en `<0.28.2`). Se conserva el extra `dev` (httpx) para la instalación con pip.
  - `[tool.pytest.ini_options]`: `testpaths`, `pythonpath` hacia `packages/shared` y `packages/incident-analyzer` (siguen sin declararse) y `addopts = -p no:logging`.
  - `[tool.coverage]`: `source = ["app"]`, `branch = true` y `show_missing = true`.
  - Comentarios corregidos: la orden de pip incluye `packages/shared`; ya no dice «sin pytest».
- **`uv.lock`:** solo añade `pytest` 9.1.1, `pytest-cov` 7.1.0 y sus transitivas (`coverage` 7.16.2, `pluggy`, `iniconfig`, `packaging`, `pygments`, `colorama`, `tomli`). Ninguna versión existente cambia.
- **`services/api/.gitignore` (nuevo):** `.coverage`, `.coverage.*` y `htmlcov/`.
- **Docs:** `SPECS.md` D-API-3 y el README de `services/api` (dependencias y tests con uv) ya no dicen que no hay pytest.

**Hallazgos verificados:**
- **uv 0.12.21:** `uv run` sincroniza de forma inexacta y conserva los paquetes instalados con pip; `uv sync` es exacto y los desinstala. Probado en un venv desechable con `UV_PROJECT_ENVIRONMENT` y después en el real.
- **`pythonpath`:** con los dos paquetes desinstalados por `uv sync`, la suite pasó igual con pytest (312) en el venv desechable.
- **Plugin de logging de pytest:** añade un handler al logger raíz, así que `logging.lastResort` deja de escribir en stderr. Con él fallaban 4 tests de scripts (base corrupta en `create-admin`, el seed de proveedores y el seed del gestor), que esperan la línea `storage … is unavailable` en stderr. No es un bug del producto. Se desactiva con `-p no:logging`, sin tocar los tests.
- **Control de aplicaciones de Windows (error 4551):** bloquea algunos lanzadores `.exe` de uv sin firmar (`pytest.exe` en `%TEMP%` y `coverage.exe` en el venv real; `pytest.exe` del venv real sí arranca). Se usa `python -m coverage`. No se tocó la política.

**Validación ejecutada:**
- `pip list` del venv real antes y después: solo altas (los 8 paquetes nuevos), y `nexova-shared` y `nexova-incident-analyzer` siguen instalados.
- `uv run pytest`: 312 OK (1904 subtests), con un único aviso, el `StarletteDeprecationWarning` conocido.
- Comando `unittest` de `AGENTS.md` §4: 312 OK. `packages/shared`: 81 OK. `packages/incident-analyzer`: 121 OK (7 omitidos).
- **Cobertura de partida** (suite existente): global 97 %; módulo de autenticación (`app/auth/*` y `app/routes/{auth,users,profiles}.py`) **96 %**, con `uv run python -m coverage report --include=… --fail-under=70`.
- `services/api/data/*.json` sin cambios (huella antes y después). Venvs desechables borrados.

---

## 2026-10-10 — Auditoría de gestión de errores: cierre (W1, verificación final de la rama)

**Estado: hecho, validado y comiteado** en `feature/error-handling-audit`, que sale de `main` en `6dfa013` (merge de la PR #17). ~~Pendiente: push y PR, que hace el usuario.~~ *Corregido el 2026-10-10: integrada en `main` con la PR #18 (merge `843ae26`).*

**Origen:** auditoría de solo lectura del 2026-10-09 sobre todo el código de producción. Encontró 2 hallazgos ALTO, 6 MEDIO y 10 BAJO, ninguno crítico; el informe se entregó en la conversación y no está versionado. El usuario pidió corregirlos por fases.

**Commits de la rama:**

| Commit | Fase | Qué |
|---|---|---|
| `24f0e0d` | `fix(api)` | A1: `http.client.HTTPException` → `EmailDeliveryError`. A2: almacenamiento TinyDB ilegible o corrupto → 503 `storage_unavailable` (`GuardedJSONStorage`) |
| `a6f3722` | `fix(scripts)` | S1–S4: el seed del gestor, `uv run seed`, `create-admin` y `analyze.py` terminan con mensaje en stderr y código de salida, sin traceback; `describe_os_error` |
| `2454dcd` | `fix(backoffice)` | B1–B4: `app/error.tsx`, `global-error.tsx` y `not-found.tsx`; textos sin detalles técnicos; reintento del guard con carga; `blob()` con el mismo tratamiento que `json()` |
| `dc91918` | `fix(tracker)` | T1–T4 y T6: límites de error; textos fijos por tipo (`describeApiError`); timeout que cubre el cuerpo; `classifySubmitError` y bloqueo del reenvío; reintento del guard con carga |
| `899ce1e` | `fix(website)` | W1: `uis/website/404.html` con navegación, enlace a inicio y al formulario, y rutas absolutas |
| este | `docs(memory-bank)` | Cierre y sincronización |

**Verificación final de `main..HEAD`:**
- **Validaciones de AGENTS.md §4, de `main` a `HEAD`:**
  - `services/api`: 289 → 312;
  - `packages/incident-analyzer`: 118 → 121 (7 omitidos);
  - `packages/shared`: 81 → 81;
  - `src/`: 97 → 97;
  - backoffice: tests 332 → 344; `tsc` y `lint` limpios; `build` OK (12 rutas en los dos);
  - tracker: tests 35 → 55; `tsc` limpio; `lint` con los mismos 4 errores anteriores; `build` OK (9 rutas).
- **Cómo se midió `main`:** en un worktree temporal de `6dfa013`. El `build` de las apps no pudo ejecutarse allí, porque Turbopack rechaza el enlace de `node_modules` que apunta fuera del proyecto. El de referencia es el del propio repo al empezar las fases 3 y 4, con el código de cada app idéntico a `main` (`git diff --quiet` lo confirma). En un checkout recién hecho, `tsc` de las apps necesita antes los tipos que Next genera en `.next/types`.
- **Diff limpio:** `git diff main..HEAD --stat` es idéntico con y sin `--ignore-cr-at-eol`. No hay `.vscode/`, `.env`, `*.tsbuildinfo`, `.next/` ni bases de datos, ni cambios en `package.json`, `pyproject.toml` o lockfiles.
- **Búsquedas en las líneas añadidas de producción:** sin `console.*`, `except Exception`, `except: pass` ni `error.message` en JSX. «código» y «traceback» solo aparecen en comentarios y docstrings.
- **Búsquedas en todo el código de las dos apps:** `NEXT_PUBLIC_` solo aparece en la lectura de `process.env`, en comentarios JSDoc, en el mensaje interno de `ApiConfigError` del backoffice (nunca se muestra: la UI lo traduce) y en el fail-fast del tracker (SPECS §3.2, solo en build y dev).

**Lo que NO se hizo y por qué:**
- **B5, contacto de soporte en los errores:** el contexto no define ningún contacto y no se inventa. Los errores ofrecen «Reintentar» y un enlace a inicio.
- **T5, señal de cancelación externa en `request()` del tracker:** se acerca más a un refactor que a gestión de errores.
- **`BrokenPipeError` de `analyze.py`:** en Windows, escribir en una tubería cerrada da `OSError` con `EINVAL` y no `BrokenPipeError`, así que no hay un test fiable y pequeño.
- **Riesgo de duplicación de `IncidentRepository.seed`:** dos escrituras no atómicas. Queda registrado y sin corregir, porque es consistencia de datos y no gestión de errores (ver "Decisiones y problemas conocidos").
- **Consola del navegador en los límites de error:** React registra en la consola, con su mensaje y su traza, los errores que capturan `error.tsx` y `global-error.tsx`. El código propio no los registra. La regla para que no expongan datos (ningún error lanzado en producción lleva datos de la API o del usuario en su mensaje) está en el `CLAUDE.md` del backoffice.

**Smoke test manual de los caminos normales:** lo verificó **el usuario a mano el 2026-10-10**, con bases temporales y siguiendo la guía (`docs/error-handling-audit.md` §7.5). Todo funcionó:
- registro, login, perfil y logout;
- `/incidents` con el fixture de aceptación (100/96/4) y exportación de `results.csv`;
- `/suppliers`: alta con error de campo sin «(422)», alta correcta, cambio de tarifa y suspensión;
- `/incident-manager`: validación en cliente, resalte de `branch`, alta y `open → in_progress` con el resumen actualizado;
- not-found del backoffice y del tracker, y `404.html` de la web en escritorio y a 375 px;
- tracker: listado, filtros, detalle, y una nota añadida y borrada;
- con la API parada, mensaje sin detalles técnicos y recuperación con «Reintentar».

**No se probaron a mano** la creación ni la edición de candidaturas: escriben en la API de 4Geeks y el tracker no permite borrarlas. Lo cubren los tests automáticos (`errors.test.mjs` y `production-source.test.mjs` del tracker).

**Informe y guía de revisión:** [`docs/error-handling-audit.md`](../docs/error-handling-audit.md). Incluye el informe completo de hallazgos (A1–W1), lo revisado como correcto por diseño, el antes y el ahora para el usuario, la trazabilidad de los 8 criterios del ticket y las guías de verificación manual. Se añadió después del cierre, con un commit `docs` propio.

**Pendientes:** ~~el push y la PR (los hace el usuario)~~ (hecho: PR #18, merge `843ae26`) y la revisión de las decisiones de la auditoría: el 503 nuevo en el contrato de la API, `retry()` de Next 16 y el bloqueo del reenvío en el tracker.

---

## 2026-10-10 — Auditoría de gestión de errores: T1–T4 y T6 en `uis/talent-pipeline-tracker`

**Estado: hecho, validado y comiteado** (`dc91918`, `fix(tracker)`), en `feature/error-handling-audit`, después de `2454dcd`. Es la cuarta fase pedida por el usuario.

**T5 no se hace** (señal de cancelación externa): se acerca más a un refactor que a gestión de errores.

**Qué se hizo:**
- **T1, límites de error:** se crean `app/error.tsx`, `app/global-error.tsx` y `app/not-found.tsx`, y se conserva `app/candidates/[id]/not-found.tsx`.
  - **Documentación:** la de Next 16.3.2 del tracker es idéntica a la del backoffice (mismo `error.md` y mismo `ErrorInfo` con `retry` y `reset`).
  - **Comportamiento:** textos fijos, «Reintentar» con `retry()` y enlace a `/`. El error no se lee. `global-error` tiene su propio `<html>`/`<body>` y no usa sesión, guard ni avisos.
- **Fail-fast de §3.2 (sin cambios):** con `NEXT_PUBLIC_API_URL` vacía, `npm run build` falla igual con y sin los límites («Error occurred prerendering page "/"… NEXT_PUBLIC_API_URL no está definida»).
  - **En `next dev`, antes:** se veía la página por defecto de Next, en inglés («This page couldn’t load — Reload to try again, or go back»).
  - **En `next dev`, ahora:** se ve `global-error.tsx` («Algo ha fallado / No se pudo cargar el tracker», con «Reintentar» y enlace a inicio).
  - **Igual en los dos casos:** el overlay de desarrollo de Next muestra el mensaje con la variable que falta (solo en dev).
- **T2, ningún texto técnico en la UI:**
  - `describeApiError` da un texto fijo por tipo (`classifyApiError` + `API_ERROR_MESSAGES`: red, timeout, 401, 404, 4xx, 5xx, respuesta ilegible y desconocido). El 422 sigue con los `msg`.
  - El `ApiError` genérico ya no lleva «La API respondió con el código N». Hay clases nuevas: `UnreadableResponseError` (con `status`), `UnknownClientError` y `asError`.
  - Los normalizadores lanzan `ResponseShapeError` (`lib/response-shape-error.ts`, sin efectos al importarse) en vez de `Error`. El mensaje sigue siendo descriptivo, pero no se muestra.
  - `candidate-list`, `candidate-detail` y `notes-list` usan `describeApiError` en vez de `error.message`. Los hooks usan `asError` en vez de `new Error(String(error))`.
  - `profile-view` sigue mostrando `load.message`, que ya sale de `describeApiError`. `auth-guard` pasa a usar el tipo de error (T6). `candidate-status-controls` y `note-form` ya usaban `describeApiError`.
- **T3, `request()`:** el temporizador cubre la petición y la lectura del cuerpo (`readJson`). El `finally` exterior lo limpia en todos los caminos.
- **T4, `lib/submit-error.ts` (`classifySubmitError`, función pura):**
  - `validation` (422 por campo);
  - `saved_unreadable` (2xx ilegible o fuera de contrato): «Se guardó, pero no se pudo leer la respuesta; recarga el listado.»;
  - `uncertain` (timeout);
  - `not_saved` (red, 4xx o 5xx).

  `candidate-form` bloquea el reenvío en `saved_unreadable` y `uncertain`. El `<dialog>` de `components/ui/modal.tsx` no desmonta su contenido al cerrarse, así que `candidate-list` y `candidate-detail` montan un formulario nuevo en cada apertura (`key` renovada en `openCreate` y `openEdit`). Así el bloqueo y los errores no pasan al siguiente intento. Efecto visible: «Nueva candidatura» se abre siempre vacía; antes conservaba lo escrito, también después de crear una.
- **T6, guard:** estado `retrying` (se emite solo en el reintento forzado del mismo token) y `sessionErrorCopy(kind)` con un texto por tipo de error. «Reintentar» muestra «Reintentando…» con el spinner y queda deshabilitado.
- **Optional chaining (sin cambios):** los campos anulables (`linkedin_url`, `cv_url`, `profile` y sus campos, `errors.form`) ya tienen fallback.
- **Docs:** `CLAUDE.md` (nueva sección «Errores»), `SPECS.md` §5.4 (mensaje legible) y `README.md` (tests).

**Validación ejecutada:**
- **Tracker:**
  - `tsc` limpio;
  - `lint` con los mismos 4 errores `set-state-in-effect` anteriores (antes `use-notes:63`, `use-record-detail:58` y `use-records:75` y `:112`; ahora 64, 58, 76 y 113, por un `import` más) y ninguno nuevo;
  - `build` OK;
  - tests: de 35 a **55 OK** (+15 en `errors.test.mjs` y +5 en `production-source.test.mjs`). Se actualizó la aserción del texto de red en `auth.test.mjs`.
- **Mutaciones:** cada arreglo deshecho hace fallar su test. Los casos probados: sin `app/error.tsx`; `global-error` con `useToast`; `error.message` en `candidate-list`; `new Error(String(error))`; `describeApiError` devolviendo `error.message`; el código en el mensaje HTTP; normalizadores con `Error`; temporizador limpiado antes del cuerpo; sin el caso «se guardó»; `candidate-form` con `.message`; reintento sin `retrying`; y `candidate-list`/`candidate-detail` sin la `key` del formulario.
- **Navegador:**
  - **Montaje:** `next start` en el 3011, con un build cuya autenticación apunta a una API temporal en el 8011, bases temporales fuera del repo y un usuario desechable. La API de 4Geeks solo se leyó (listado y un detalle). Sus fallos se simularon sobrescribiendo `fetch` en la página, y el único POST lo respondió el simulador sin llegar a 4Geeks.
  - **(1) Rutas:** una ruta inexistente muestra el not-found raíz; un id inexistente, el de `candidates/[id]`.
  - **(2) Error de render** (con una ruta temporal, ya borrada): se ve `error.tsx` dentro del layout y «Reintentar» recupera la vista.
  - **(3) Listado, detalle y notas:** con un 500, con la red caída y con el cuerpo colgado (timeout real de 20 s) se ven el texto del servidor, el de conexión y el de «tardó demasiado», con «Reintentar» y sin ningún código.
  - **(4) T4:** se ve el mensaje «Se guardó…» en el formulario y en el aviso, y el botón de enviar queda deshabilitado.
  - **(5) `auth.json` corrupto:** el guard muestra «El servidor tuvo un problema al comprobar tu sesión…». Al reintentar se ve «Reintentando…» con el spinner y el botón deshabilitado. Al restaurar el archivo, la vista se recupera.
  - **(6) Consola:** sin datos sensibles.
- **Sin tocar:** no se usaron los puertos 3000, 3001 ni 8000, ni `services/api/data/`.

---

## 2026-10-10 — Auditoría de gestión de errores: B1–B4 en `uis/backoffice`

**Estado: hecho, validado y comiteado** (`2454dcd`, `fix(backoffice)`), en `feature/error-handling-audit`, después de `a6f3722`. Es la tercera fase pedida por el usuario: solo B1–B4.

**B5 no se hace** (contacto de soporte en los errores): el contexto no define ningún contacto y no se inventa. Los errores ofrecen «Reintentar» y un enlace a inicio.

**Qué se hizo:**
- **B1, límites de error (Next 16.3.2):** se crean `app/error.tsx`, `app/global-error.tsx` y `app/not-found.tsx`.
  - **Firma de props:** según `node_modules/next/dist/docs/01-app/03-api-reference/03-file-conventions/error.md` y `dist/client/components/error-boundary.d.ts`, es `{ error: Error & { digest?: string }; retry: () => void }`, y también existe `reset`.
  - **Comportamiento:** textos fijos en español, «Reintentar» con `retry()` y enlace a `/`. El error no se lee: ni `console.*`, ni `message`, `digest` o `stack`.
  - **`global-error.tsx`:** tiene su propio `<html>`/`<body>`, importa `globals.css` y no usa ni la sesión ni el guard.
- **B2, textos de error:** se quitan `«(422)»`, `«services/api»` y `«NEXT_PUBLIC_API_URL»` de `supplier-error`, `incident-error`, `auth-error` y `analysis-error`, y también del estado vacío de `supplier-directory-view`, que mostraba `«uv run seed» en services/api`. Las menciones a «la API» pasan a «el servidor». Se mantienen el tipo de error y su acción.
- **B3, reintento del guard:** nueva acción `validation_started` y nuevo estado `retrying` en `hooks/use-auth-session.ts`.
  - **Cuándo se emite:** solo en el reintento forzado. La primera validación de un token ya se ve como `checking`, y un 401 sigue sin despachar nada.
  - **Ruta:** `routeAccess` trata `retrying` como `error`, así que el aviso se mantiene y el botón muestra «Reintentando…» con spinner y `aria-busy`.
  - **Textos:** `sessionErrorCopy` da uno por tipo de error (red, timeout, servidor, configuración, respuesta inesperada y un genérico).
- **B4, `lib/api-client.ts`:** `blob()` trata los errores como `json()`. Los aborts se relanzan y `send` los convierte en abort o timeout; cualquier otro fallo de lectura pasa a ser `ApiNetworkError`.
- **Optional chaining (sin cambios):** todos los campos anulables de los tipos que producen los normalizadores ya tienen fallback al mostrarse. Son `percentage`, `average_score`, `contract_renewal_date`, `contact_email`, `notes`, `profile` y sus campos, y `field`.
- **Docs:** `uis/backoffice/CLAUDE.md` (reglas de límites de error, textos sin detalles técnicos y reintento del guard) y `README.md` (revisión estática).

**Validación ejecutada:**
- **Backoffice:**
  - `tsc` y `lint` limpios;
  - `build` OK (12 rutas, las mismas que en `main`: `app/not-found.tsx` sustituye a la página `/_not-found` por defecto). *Corregido en el cierre: decía «13 rutas»;*
  - tests: de 332 a **344 OK** (+2 `production-source`, +2 `api-client`, +5 `use-auth` y los tests por archivo de los 3 archivos nuevos).
- **Mutaciones:** cada arreglo deshecho hace fallar su test. Los casos probados: sin `app/error.tsx`; `global-error` usando la sesión; `supplier-error` original; `use-auth-session` y `auth-routes` originales; reintento sin `validation_started`; y `api-client` original.
- **Navegador:**
  - **Montaje:** `next start` en el 3010, con un build que apunta a una API temporal en el 8011, bases temporales fuera del repo y CORS para el 3010. Un usuario de prueba desechable.
  - **(1) Ruta inexistente:** se ve «Página no encontrada» con el enlace a `/`.
  - **(2) Error de render:** se provocó con una ruta temporal, ya borrada. Se ve «Algo ha fallado / No se pudo mostrar esta página» dentro del layout, y «Reintentar» recupera la vista.
  - **(3) API parada:** `/suppliers`, `/incident-manager` (resumen y listado) e `/incidents` muestran «No se pudo conectar con el servidor. Comprueba tu conexión e inténtalo de nuevo. Si el problema continúa, avisa al equipo técnico.».
  - **(4) `auth.json` corrupto:** el guard muestra «No se pudo comprobar la sesión. El servidor tuvo un problema al comprobar tu sesión. Inténtalo de nuevo en unos minutos.», con «Reintentar» y «Cerrar sesión». La API registró `storage auth is unavailable: JSONDecodeError`.
  - **(5) Reintento:** con `fetch` retrasado, «Reintentar» pasa a «Reintentando…», deshabilitado, con `aria-busy` y spinner, y el aviso se mantiene. Al restaurar `auth.json`, el reintento recupera la vista.
  - **Consola:** solo errores de red del navegador (códigos 401, 404 y 503 y conexiones rechazadas, sin cuerpos ni tokens) y el error provocado a propósito, que React registra con su mensaje y su traza.
  - **Después:** sin ruta temporal, build final con la configuración normal y puertos 3010 y 8011 libres.
- **Sin tocar:** no se usaron los puertos 3000 ni 8000, ni `services/api/data/`.

---

## 2026-10-10 — Auditoría de gestión de errores: S1–S4 (scripts y CLIs sin traceback)

**Estado: hecho, validado y comiteado** (`a6f3722`, `fix(scripts)`), en `feature/error-handling-audit`, después de `24f0e0d` (A1 y A2). Es la segunda fase pedida por el usuario: solo S1–S4.

**Qué se hizo:**
- **S1, `scripts/seed_incidents.py`:**
  - Solo se protege la llamada `IncidentRepository(db_path).seed(...)`, y solo contra `StorageUnavailableError`, que es la forma en que llega un fallo de TinyDB desde A2.
  - Mensaje en stderr con el nombre del archivo, nunca la ruta completa ni `str(exc)`.
  - Código `2` ("entorno"). El docstring, el README de `services/api` y la guía de revisión del gestor ya lo dicen.
- **S2, `services/api/app/seed.py` (`uv run seed`):** `main()` captura `ConfigError` de `Settings.from_env()` y `StorageUnavailableError` del repositorio, cada uno en su `try`. Ambos dan mensaje en stderr y `sys.exit(1)`. Los mensajes de `ConfigError` nombran la variable, nunca su valor.
- **S3, `services/api/app/auth/create_admin.py`:** `run()` devuelve 1, sin traceback y sin crear nada, en tres casos tratados por separado:
  - `ConfigError`;
  - `EOFError` o `KeyboardInterrupt` de `input()` y `getpass` («Operación cancelada. No se ha creado ningún usuario.»);
  - `StorageUnavailableError`.

  La contraseña no aparece en ninguna salida.
- **S4, `scripts/analyze.py`:**
  - Ctrl+C en la pregunta de exportar equivale a «no exportar» (código `0`).
  - `describe_os_error` sustituye `error.strerror` (que puede ser `None`) por el nombre de la clase.
  - `scripts/seed_incidents.py` usa también su propia copia de `describe_os_error` al leer el CSV, para que los scripts no se importen entre sí.
  - **No hecho:** el `BrokenPipeError` al redirigir la salida a `head`. En Windows, escribir en una tubería cerrada da `OSError` con `EINVAL` y no `BrokenPipeError`, así que no hay un test fiable y pequeño. Queda documentado.
- **Registro en stderr:** en los scripts, el logger `nexova.api` no tiene handler, así que `log_storage_failure` sale por el handler de último recurso de `logging` (`storage <almacén> is unavailable: <Clase>`), justo antes del mensaje del script.
  - **Se acepta:** no es un duplicado. Aporta la clase del error (`JSONDecodeError` frente a `PermissionError`), que el script no conoce porque `StorageUnavailableError` no arrastra la excepción original.
  - **Sin datos sensibles:** no lleva ruta ni contenido.
- **Tests:**
  - `test_incident_manager_seed.py` +3 (`--db` como directorio, base corrupta y `OSError` sin `strerror` al leer el CSV);
  - `test_suppliers_seed.py` +2 (configuración de email incompleta y base corrupta);
  - `test_create_admin.py` +4 (EOF, Ctrl+C, base corrupta y `ConfigError`); la base común se extrajo a `CreateAdminTestCase`;
  - `packages/incident-analyzer/tests/test_cli_errors.py` nuevo, con 3 tests;
  - los tests de `KeyboardInterrupt` convierten una regresión en un `fail` normal, para no abortar la suite.

**Validación ejecutada:**
- **Suites:** `services/api` pasa de 303 a **312 OK**; `packages/incident-analyzer` de 118 a **121 OK** (7 omitidos).
- **Mutaciones:** devolviendo cada archivo a `24f0e0d`, fallan los 12 tests nuevos (3 + 2 + 4 + 3).
- **Seed del gestor:** dos ejecuciones sobre una base temporal con el fixture de aceptación dan 96 insertadas y luego 0.
- **`uv run seed`:** dos ejecuciones con `SUPPLIERS_DB_PATH` temporal dan 15 y luego 0. uv reconstruyó el paquete editable de la API; el núcleo y `nexova_shared` siguieron instalados.
- **Bases de prueba:** siempre fuera del repo, sin tocar `services/api/data/`.

**Observación, sin corregir:** riesgo de duplicación en `IncidentRepository.seed`, registrado en "Decisiones y problemas conocidos". Por eso el mensaje de S1 no promete «no se ha insertado nada».

---

## 2026-10-10 — Auditoría de gestión de errores: A1 (respuestas cortadas de Resend) y A2 (TinyDB no disponible → 503) en `services/api`

**Estado: hecho, validado y comiteado** (`24f0e0d`, `fix(api)`), en la rama `feature/error-handling-audit`, creada desde `main` en `6dfa013` (merge de la PR #17). Origen: auditoría de solo lectura del 2026-10-09 sobre todo el código de producción (backend, scripts, backoffice, tracker y web). Encontró 2 hallazgos ALTO, 6 MEDIO y 10 BAJO, ninguno crítico. El informe se entregó en la conversación y no está versionado. El usuario pidió implementar solo A1 y A2. El resto sigue pendiente (ver "Próximos pasos").

**Qué se hizo:**
- **A1 (era L-4 de AUTH-03):** `app/auth/email.py` añade `http.client.HTTPException` a los errores que `ResendEmailSender.send` convierte en `EmailDeliveryError` (con `from None`). `IncompleteRead`, `BadStatusLine` y `LineTooLong` no son `OSError`. Hasta ahora escapaban de la tarea en segundo plano y las registraba el middleware del 500 ("unhandled error"), no `log_email_delivery_failure`.
- **A2:** nuevo `app/core/storage.py` con `GuardedJSONStorage`, el storage de TinyDB que usan los tres repositorios (`database.py`, `auth/repository.py`, `modules/incident_manager/repository.py`).
  - **Qué captura:** solo los fallos del archivo. Es decir, `OSError` en la apertura, `read`, `write` y `close`; `JSONDecodeError` y `UnicodeDecodeError` en `read`; y JSON que no tiene la forma `{tabla: {id: documento}}`.
  - **Qué responde:** 503 `storage_unavailable` con el `detail` fijo `storage is temporarily unavailable`.
  - **Qué registra:** la nueva `log_storage_failure` de `core/errors.py` solo anota el almacén (`suppliers`, `auth`, `incidents`) y la clase de la excepción.
  - **Ámbito de la captura:** no envuelve el `yield` de los context managers. Si lo hiciera, el `ValidationError` de Pydantic y `InvalidStatusTransitionError` (ambos `ValueError` lanzados dentro del `with`) acabarían en un 503 falso.
  - **Sin la excepción original:** el error se lanza fuera del `except`, así que no arrastra ni `__cause__` ni `__context__`. Importa porque `JSONDecodeError.doc` guarda el archivo entero.
- **Docs:**
  - `services/api/SPECS.md`: 503 en §4, §5, §12, §18, §31 y §33.
  - `services/api/README.md`: endpoints, códigos de proveedores, tabla de tests y estructura.
- **Memory-bank:** se corrige que el gestor centralizado de incidencias figuraba "pendiente de PR". Se integró en `main` con la PR #17 (merge `6dfa013`, 2026-10-08).

**Validación ejecutada:**
- **Suite de `services/api`:** 289 → **303 OK**. Son +2 en `test_password_reset.py` (con 3 subtests cada uno) y +12 en el nuevo `test_storage.py`.
- **Mutaciones:**
  - con el `email.py` anterior fallan los 6 subtests de A1;
  - sin la traducción del storage fallan los 6 tests de corrupción;
  - con la captura "ingenua" alrededor del `yield` fallan los 2 tests de regresión del ámbito.
- **Paquetes Python sin ejecutar:** no se tocaron `packages/` ni `scripts/`, así que no se ejecutaron sus suites.
- **Prueba manual:**
  - **Montaje:** uvicorn en el puerto 8011 con tres bases temporales en el scratchpad, fuera del repo, y una clave JWT generada al momento. No se tocaron `services/api/data/` ni la API del usuario.
  - **Bases sanas:** 200; el 422 de proveedores y el 400 del gestor se mantienen.
  - **Bases corruptas:** `suppliers.json` corrupto, `incidents.json` no UTF-8 y `auth.json` corrupto responden 503 en `/suppliers`, `/api/incidents/summary`, `/auth/login`, `/auth/me` y en una ruta protegida.
  - **Recuperación:** al restaurar `auth.json`, el login vuelve a responder (401 con un email inexistente).
  - **Log:** solo `storage <almacén> is unavailable: <Clase>`, sin rutas ni emails.

**Efectos colaterales conocidos:**
- `scripts/seed_incidents.py`, `uv run seed` y `create-admin` también usan estos repositorios. Con una base corrupta ahora reciben `StorageUnavailableError` (antes, `JSONDecodeError`) y seguían terminando con traceback (S1–S3). *(Resuelto el 2026-10-10 en la entrada de arriba.)*
- **Frontends sin cambios:**
  - **Backoffice:** el 503 es «Error del servidor». En el guard de sesión es «No se pudo comprobar la sesión», con «Reintentar».
  - **Tracker:** las rutas de auth muestran «La API respondió con el código 503» (hallazgo T2).

---

## 2026-10-07 — Gestor centralizado de incidencias: scroll horizontal en móvil (`/incident-manager`)

**Estado: hecho, validado y comiteado** (commit aparte, después de F6 `ca0bf00`), en `feature/centralized-incident-manager`. *(Corregido el 2026-10-10: integrado en `main` con la PR #17, merge `6dfa013`, 2026-10-08.)*

**Fallo, encontrado y diagnosticado por el usuario en el navegador:**
- A 375 px, `/incident-manager` tenía scroll horizontal en toda la página (scrollWidth 673 frente a clientWidth 375).
- Causa: las etiquetas `<label className="sr-only">` de la columna Estado de `components/incident-manager/incident-table.tsx` son `position: absolute`, y el contenedor `overflow-x-auto` no era su bloque contenedor.

**Qué se hizo:**
- `relative` en ese contenedor. Sin cambiar el `min-w` de la tabla ni quitar las etiquetas accesibles.
- Test estático nuevo en `tests/production-source.test.mjs`: todo `overflow-x-auto` de `components/` debe llevar `relative`. Lleva una lista explícita de excepciones pendientes y falla si una se corrige sin retirarla de la lista. Una mutación (quitar `relative`) lo hace fallar.
- Docs: regla en `uis/backoffice/CLAUDE.md` (Arquitectura). La guía de revisión pasa el viewport móvil a "verificado por el usuario", citando el fallo y su arreglo.

**Mismo patrón detectado (solo lectura, sin corregir):**
- `components/suppliers/supplier-table.tsx`: `<caption className="sr-only">` y la etiqueta `sr-only` del editor de tarifa, que solo existe con el editor abierto.
- `components/incidents/distribution-table.tsx`, `invalid-breakdown-table.tsx` y `satisfaction-panel.tsx` (`/incidents`): `<caption className="sr-only">`.
- No se ha medido si llegan a ensanchar la página.

**Validación ejecutada:**
- Backoffice: `tsc`, `lint` y `build` limpios; tests 332 OK (331 + 1).
- Navegador, sobre los servidores de desarrollo del usuario (backoffice en el 3000 y API en el 8000):

  | Ruta | 375 px | 1280 px |
  |---|---|---|
  | `/incident-manager` | 375 = 375 | 1265 = 1265 |
  | `/incident-manager/new` | 375 = 375 | 1265 = 1265 |

  - A 375 px, la tabla conserva su scroll propio (768 frente a 341).
  - Sin `relative` (desde la consola), scrollWidth vuelve a 672.

**Incidencia de la sesión:**
- Los puertos 3000 y 8000 los ocupaban los servidores del usuario, así que la API temporal no arrancó.
- El usuario de prueba `qa-mobile@example.test` se creó por error en la API del usuario. Se usó solo para esta verificación de solo lectura y después se borró (`DELETE /users/{id}` → 204; el login posterior da 401).

---

## 2026-10-07 — Gestor centralizado de incidencias, F6: documentación de cierre (proyecto hecho; integrado en `main` con la PR #17)

**Estado: hecho y comiteado** (commit de F6 `ca0bf00`, solo documentación) en `feature/centralized-incident-manager`, después de F5 (`7ce4101`). **El proyecto completo (F1–F6) está hecho.** *(Corregido el 2026-10-10: entonces estaba sin push ni PR. Se integró en `main` con la PR #17, merge `6dfa013`, 2026-10-08.)*

**Decisiones:** P4-1…P4-13 (ver la entrada de F1 y `services/api/SPECS.md` §29) son **decisiones del usuario** tomadas al aprobar el plan, incluido el cambio de P4-5 en F2 (SHA-256 en `seed_keys`). **No las han revisado ni aprobado el tech lead ni la CTO.**

**Qué se hizo:**
- **`docs/centralized-incident-manager-review.md` (nuevo), guía de revisión** con:
  - comandos exactos de Windows PowerShell: venv con los tres paquetes editables, seed con el fixture sintético y su salida esperada (96 insertadas / 4 inválidas; la segunda vez, 0), API, backoffice, comprobación de `/api/incidents/summary` y comandos de las suites con sus totales;
  - tabla de trazabilidad "Qué evaluaremos" → implementación → test, indicando qué puntos no tienen test automático (el resalte de `branch`, el spinner y el `disabled` en el DOM, la llamada del componente a la validación y la estructura de carpetas);
  - lista de lo no verificado.
- **Comandos de la guía comprobados en PowerShell:**
  - seed dos veces con `INCIDENTS_DB_PATH` (96 y luego 0);
  - `Invoke-RestMethod` de login y `/summary` contra una API sobre bases temporales, que devolvió exactamente la tabla documentada.
- **`services/api/SPECS.md`:** §33 enlaza la UI y la guía (se quita "Pendiente: la UI (F5)"); §29 aclara que las decisiones son del usuario.
- **Enlaces a la guía** desde el README de `services/api`, `uis/backoffice/README.md`, `packages/shared/README.md` y `AGENTS.md` §4 (el gestor ya no figura "en curso").
- Sin cambios de código de producción ni de tests.

**Validación ejecutada (última pasada):** `packages/shared` 81 OK; analizador 118 OK (7 skipped); `services/api` 289 OK; `src/` 97 OK; backoffice `tsc` y `lint` limpios, `build` OK y 331 tests OK.

**Pendiente / no verificado** (detalle en la guía de revisión):
- CSV real ausente: la aceptación (96; 27/56/13; 49/35/12) solo se comprobó con el fixture sintético.
- Verificación visual, móvil y con lector de pantalla pendiente.
- Con un filtro activo, una incidencia que cambia de estado sigue en el listado hasta la siguiente carga (decisión de implementación, no fijada por ninguna fuente).
- Un 400 con `field` no se puede provocar desde la UI real (solo cubierto por tests).
- No se hizo el recorrido manual en `/docs`.
- No hay soporte bilingüe (no existía en hitos anteriores).
- Revisión de P4-1…P4-13 por el tech lead o la CTO.
- ~~Push y PR~~: hecho, PR #17, merge `6dfa013` (2026-10-08).

---

## 2026-10-07 — Gestor centralizado de incidencias, F5: UI en `uis/backoffice` (`/incident-manager`, `/incident-manager/new`)

**Estado: hecho, validado y comiteado** (commit de F5), en `feature/centralized-incident-manager`, después de F4 (`d7ce215`). Sin tocar `services/` ni `packages/`; sin dependencias nuevas. El usuario autorizó ampliar el "Alcance actual" de `uis/backoffice/CLAUDE.md` con una cuarta pieza.

**Qué se hizo:**
- **Rutas y menú:**
  - `/incident-manager` (resumen arriba y listado debajo; menú «Incidencias»);
  - `/incident-manager/new` (formulario; menú «Registrar incidencia»);
  - `/incidents` (el analizador) sin cambios.
- **Capas:** páginas Server Component → vistas cliente (`components/incident-manager/`) → `hooks/use-incident-board.ts`, `use-incident-summary.ts` y `use-incident-form.ts` (reducer puro + sesión sin React + hook) → `services/incident-manager.service.ts` → `lib/api-client.ts`. `unknown` solo en `services/normalizers.ts`.
- **Vocabulario** en `types/incident-manager.ts` (excepción documentada, como `/suppliers`): enums, `BRANCH_LABELS`, `INCIDENT_TRANSITIONS` y `TITLE_MAX_LENGTH`. Valores literales; etiquetas solo en `branch`.
- **Formulario:**
  - campos `title` (con contador), `description`, `category`, `origin`, `branch` (siempre visible y obligatorio) y `status` en solo lectura (`open`, que se envía en el body);
  - validación en cliente antes de enviar (obligatorios y título ≤ 120), sin petición de red si no pasa;
  - con `origin = branch`, `branch` se resalta con borde, fondo y texto de ayuda;
  - spinner y botón deshabilitado durante el envío;
  - tras el éxito, confirmación y formulario limpio (`formKey` como `key`).
- **Errores:** el normalizador descarta el `message` del servidor y el servicio elige un texto en español por `code`, `field` y `error`; el error se muestra junto a su campo.
- **Listado:**
  - filtros `status`/`origin`/`branch` enviados a la API;
  - cuatro estados (`boardView`): cargando, error con «Reintentar», vacío sin tabla y con datos;
  - cambio de estado por fila solo con transiciones válidas (los finales muestran «Estado final»), optimista con reversión y aviso si falla;
  - tras un cambio correcto se recarga el resumen.
- **Resumen:** hook propio, con carga y error propios. El normalizador convierte cada diccionario de la API en una lista `{value, count}` en el orden del CONTEXT, para no usar aserciones de tipo, prohibidas por el test estático.
- **Tests** (runner nativo de Node 24): `incident-manager-contract`, `incident-manager.service` y `use-incident-manager` (nuevos), `production-source` (ampliado) y `support/incident-fakes.mjs`.
- **Docs:** `uis/backoffice/CLAUDE.md` (cuarta pieza y sección propia), `uis/backoffice/README.md`, `uis/README.md`, `uis/README.es.md` y `AGENTS.md` §4 (verificación en el navegador del gestor).

**Validación ejecutada:**
- Backoffice: `npx tsc --noEmit` y `npm run lint` limpios; `npm run build` OK (rutas estáticas `/incident-manager` y `/incident-manager/new`); tests 331 OK frente a la línea base de 263 (+68).
- Navegador (API real en el puerto 8000 con bases TinyDB temporales fuera del repo, seed del fixture de aceptación, usuario de prueba desechable; backoffice `npm run dev` en el 3000):
  - resumen con 96 / 27-56-13 / 49-35-12 / customer 96 / central 96;
  - cambio `open → in_progress` con el resumen recargado;
  - transición rechazada por la API (estado cambiado por fuera con curl) → la fila vuelve a `in_progress` con el aviso en español;
  - filtros `status` y `status + origin`, y estado vacío sin tabla;
  - formulario vacío → 5 errores junto a su campo y ningún `POST` en el log de la API;
  - título de 121 caracteres → error y sin `POST`;
  - resalte de `branch` (fondo, borde de 4 px y texto) que desaparece con `internal`;
  - envío con `fetch` retrasado: botón deshabilitado, «Registrando…», spinner y `aria-busy`; después, confirmación y formulario limpio;
  - fallo simulado de `/summary` → error y «Reintentar resumen» mientras el listado sigue operativo; fallo simulado del listado → error y «Reintentar» sin tabla, y recuperación;
  - menú con los dos enlaces nuevos; `/incidents` intacto;
  - consola: solo el 400 provocado a propósito.

**Pendiente / no verificado:**
- Un 400 de la API con `field` no se pudo provocar desde la UI real, porque la validación en cliente y los selectores lo impiden; lo cubren los tests del servicio.
- No se probó con lector de pantalla ni en viewport móvil.
- `services/api/SPECS.md` §33 sigue diciendo "Pendiente: la UI (F5)": corregirlo en F6 (en esta fase no se tocaba `services/`).
- F6 (docs y memory-bank finales).

---

## 2026-10-07 — Gestor centralizado de incidencias, F4: API `/api/incidents` (`services/api`)

**Estado: hecho, validado y comiteado** (commit de F4), en `feature/centralized-incident-manager`, después de F3 (`ef040f5`). Sin tocar `uis/` (F5).

**Qué se hizo:**
- **`app/modules/incident_manager/router.py`:** router propio con prefijo `/api/incidents` y JWT obligatorio (dependencia del router en `app/main.py`, incluido después del del analizador). Rutas:
  - `POST` (201, nace `open`);
  - `GET` con filtros `status`/`origin`/`branch`/`category` (AND);
  - `GET /summary`;
  - `GET /{incident_id:uuid}`;
  - `PATCH /{incident_id:uuid}/status`.
- **Ninguna regla en la API:** usa `validate_incident_fields`, `validate_filters` y `validate_status_change` (nuevas en `nexova_shared`) y `check_transition` vía el repositorio.
- **Errores solo de este router:**
  - `IncidentManagerRoute` convierte `RequestValidationError` (body no JSON, no objeto o ausente) en 400 `validation_error` con `field = "body"` y `error = "invalid_body"`. Solo usa la ubicación del error, nunca `input` ni `msg`;
  - el resto de 400 vienen de los `FieldError` de `nexova_shared`;
  - transición no permitida → 400 `invalid_status_transition`;
  - 404 `incident_not_found`; id no UUID → 404 `not_found` (convertidor `uuid`);
  - 500 opaco del middleware existente.
  - El handler global del 422 no se tocó: proveedores y auth siguen en 422.
- **Errores nuevos en `app/core/errors.py`:** `IncidentFieldsError`, `InvalidStatusTransitionApiError`, `IncidentNotFoundError`.
- **`nexova_shared`:**
  - `IncidentFilters`, `validate_filters`, `validate_status_change`, `FILTER_FIELDS`, `STATUS_CHANGE_FIELDS` y el código `invalid_body`;
  - el mensaje de campo desconocido ya no repite la clave recibida ("this field is not accepted");
  - +9 tests en `test_rules.py`.
- **Tests:** `services/api/tests/test_incident_manager_api.py`, 43 tests:
  - cada ruta con su caso feliz y cada 400 de la lista del usuario;
  - las 16 transiciones por HTTP;
  - base vacía; totales tras el seed del fixture;
  - 401 en las 5 rutas; 404;
  - 500 forzado sin traza ni mensaje, también en los logs;
  - OpenAPI;
  - no regresión: 405 de `/analyze` y `/results/export`, 404 de `/api/incidents/unknown`, 422 de `/suppliers`, `/users` y `/profiles/me`.
- **Docs:**
  - `services/api/SPECS.md`: **Parte E** (§28–§33: requisitos, decisiones P4-1…P4-13, endpoints, errores, resumen, persistencia) y referencias en §4, §7 y §20;
  - `services/api/README.md`: endpoints, sección del gestor, tests y estructura;
  - `packages/shared/README.md`;
  - `AGENTS.md` §4: verificar en `/docs`.

**Validación ejecutada:** `services/api` 289 OK (246 + 43); `packages/shared` 81 OK; analizador 118 OK (7 skipped); `src/` 97 OK. En `/openapi.json` aparecen las 5 rutas nuevas, con los filtros como `enum`.

---

## 2026-10-07 — Gestor centralizado de incidencias, F3: seed de datos históricos (`scripts/seed_incidents.py`)

**Estado: hecho, validado y comiteado** (commit de F3), en `feature/centralized-incident-manager`, después de F2 (`959a65b`). Sin rutas HTTP (F4) y sin tocar `uis/`.

**Qué se hizo:**
- **`scripts/seed_incidents.py`**, capa fina:
  - `nexova_shared.incidents.prepare_seed_batch` lee el CSV con el lector y el esquema del analizador, aplica las 7 reglas y el mapeo;
  - `IncidentRepository.seed` inserta solo lo nuevo (idempotente por el SHA-256 de la clave de origen).
- **Argumentos:**
  - el CSV es opcional; por defecto `data/raw/incidents/incidents-nexova.csv`;
  - `--db`, opcional; por defecto `INCIDENTS_DB_PATH` o `services/api/data/incidents.json`.
- **Informe final en español**, como el seeder de proveedores: filas leídas, insertadas, ya existentes, inválidas (fila + códigos de regla), no mapeables (fila + motivo), duplicadas en el archivo (fila) y total en la base. Nunca contenido de las filas.
- **Códigos de salida:** `1` si el CSV no existe, no es UTF-8 o su cabecera no tiene las columnas del analizador (no se crea la base); `2` si fallan los argumentos, la configuración o el entorno (sin el venv).
- **Entorno:** se ejecuta con el venv de `services/api`. Si `nexova_shared` o `app` no están instalados, añade sus carpetas del monorepo a `sys.path`, como `scripts/analyze.py`.
- **Tests:** `services/api/tests/test_incident_manager_seed.py` (14 tests).
- **Docs:**
  - `services/api/README.md`: sección del gestor, con el comando exacto del seed con el fixture sintético (Windows y Linux/macOS, verificado en PowerShell), tabla de tests y estructura;
  - `scripts/README.md` y `README.es.md`: tabla de scripts;
  - `AGENTS.md` §4: párrafo del gestor (el seed se verifica ejecutándolo dos veces sobre una base temporal).

**Validación ejecutada (base temporal fuera del repo, en el scratchpad de la sesión):**
- 1.ª ejecución con el fixture de aceptación: 100 filas; 96 insertadas; 4 inválidas (filas 18 `missing_client_company`, 45 `invalid_category`, 71 `invalid_email`, 93 `closed_without_score`); 0 no mapeables; 0 duplicadas; total 96; exit 0.
- 2.ª ejecución: 0 insertadas, 96 ya existentes, total 96; exit 0.
- Resumen del repositorio: open 27 / in_progress 0 / resolved 56 / discarded 13; technical_failure 49 / process_error 35 / client_complaint 12 y el resto de categorías 0; customer 96 (branch e internal 0); central 96 (resto de sedes 0).
- En el archivo de la base hay 0 apariciones de `@`, `ticket_id`, `NXV-`, `example.invalid` y `AGT-`.
- CSV inexistente → exit 1; cabecera de otro esquema → exit 1 (`missing required columns`).
- Suites: `services/api` 246 OK (232 + 14); `packages/shared` 72; analizador 118 (7 skipped); `src/` 97.

**Aviso:** en Git Bash, con la salida redirigida, las tildes del informe se ven mal, porque Python escribe en cp1252 y la terminal lee UTF-8. En PowerShell se ven bien. No se cambió la codificación de salida.

---

## 2026-10-07 — Gestor centralizado de incidencias, F2: modelo y repositorio TinyDB (`services/api`)

**Estado: hecho, validado y comiteado** (commit de F2), en `feature/centralized-incident-manager`, después del commit de F1 (`164a183`). Sin rutas HTTP todavía (F4) y sin tocar `uis/`.

**Cambio de decisión del usuario sobre P4-5 (2026-10-07):** `seed_keys` guarda el **SHA-256** de la clave de origen, no el `ticket_id` en claro, porque el CONTEXT dice que `ticket_id` no se almacena. Se aplica en `nexova_shared.incidents.source_key`, que ahora devuelve directamente el SHA-256 en hexadecimal de `ticket_id:<id>` o, si falta, de `title_created_at:<title>\n<created_at ISO>`. Así ningún objeto en memoria lleva la clave en claro. Cubierto con 3 tests nuevos en `packages/shared/tests/test_csv_mapping.py` y con uno del repositorio que busca `NXV-`, `ticket_id` y `@` en el archivo de la base.

**Qué se hizo:**
- **`app/modules/incident_manager/`:**
  - `models.py`: `Incident` (id UUID, enums de `nexova_shared`, fechas `AwareDatetime`) e `IncidentSummary` (`total` + `by_status`/`by_category`/`by_origin`/`by_branch` con todas las claves);
  - `repository.py` (`IncidentRepository`), con el mismo patrón que proveedores (lock, abrir y cerrar por operación, un worker):
    - `find` con filtros combinables (AND), de la más reciente a la más antigua (desempate por `id`);
    - `get`;
    - `create`, a partir de un `IncidentDraft` ya validado; `id` UUID v4 y `created_at` = `updated_at` en UTC;
    - `change_status`, que aplica solo transiciones válidas (`check_transition`; si no, `InvalidStatusTransitionError` sin escribir nada) y actualiza `updated_at`;
    - `summary`;
    - `seed`, idempotente por `seed_keys` (`key_sha256` + `incident_id`), con `updated_at` = `created_at` del CSV y todo en una sola operación.
  - Las lecturas **no crean el archivo**: sin base o con la base vacía devuelven `[]` y totales a cero.
- **Configuración:** `INCIDENTS_DB_PATH` (por defecto `services/api/data/incidents.json`, ignorado por git) en `app/core/config.py`, `.env.example`, README y SPECS §7. `app.modules.incident_manager` añadido a `[tool.setuptools] packages`.
- **`tests/test_architecture.py`:** nueva regla que prohíbe en `app/` cualquier literal del vocabulario del gestor (estados, orígenes, categorías, sedes y etiquetas de sede), salvo `"branch"`, que también es nombre de campo.
- **`tests/test_incident_manager_repository.py`** (26 tests): base inexistente o vacía, creación, filtros, resumen, transiciones (válidas, inválidas, finales), seed idempotente, totales del CONTEXT, privacidad del archivo y configuración.

**Validación ejecutada:** `services/api` 232 OK (205 + 26 del repositorio + 1 de arquitectura); `packages/shared` 72 OK (70 + 2 netos del cambio de P4-5); analizador 118 OK (7 skipped); `src/` 97 OK.

---

## 2026-10-07 — Gestor centralizado de incidencias, F1: validación compartida en `packages/shared`

**Estado: hecho, validado y comiteado** (commit de F1, tras el visto bueno del usuario), en la rama `feature/centralized-incident-manager` (creada desde `main` en `677e735`, merge de la PR #16). Contexto: [`docs/centralized-incident-manager.md`](../docs/centralized-incident-manager.md) (CONTEXT del proyecto, versionado en esta fase) + enunciado del proyecto (pegado por el usuario; exige `scripts/seed_incidents.py`, `packages/shared/`, endpoints `/api/incidents…` y UI de registro, listado y resumen).

**Decisiones del usuario sobre el plan (2026-10-07):**
- P4-1 (a): mover la validación a `packages/shared` y dejar el analizador como fachada.
- P4-2: 400 solo en las rutas nuevas, con una lista de errores `{field, error, message}`; un JSON mal formado también devuelve 400.
- P4-3: router aparte con id UUID (convertidor `{incident_id:uuid}`), para conservar el 405 de `GET /api/incidents/analyze`.
- P4-4: TinyDB + Pydantic.
- P4-5 (a): tabla `seed_keys` (clave `ticket_id` o `title + created_at`), fuera del modelo.
- P4-6: CSV por argumento, por defecto `data/raw/incidents/incidents-nexova.csv`, ejecutado con el venv de `services/api`; el README tendrá el comando exacto con el fixture sintético.
- P4-7: `/incident-manager` y `/incident-manager/new` en `uis/backoffice`, reutilizando `services/api`; autorizado ampliar el alcance de `uis/backoffice/CLAUDE.md`.
- P4-8: estado en solo lectura como `open`; `title` ≤ 120; `description` sin máximo.
- P4-9: JWT sin roles. P4-10: solo transiciones válidas en el listado. P4-11: valores literales, con etiquetas solo para `branch`. P4-12 y P4-13 aceptadas.

**Qué se hizo:**
- **`packages/shared/` (nuevo paquete Python `nexova_shared`, solo librería estándar):**
  - `incident_csv/`: `schema.py`, `reader.py` y `validation.py` movidos desde el analizador sin cambios de comportamiento (`SCORE_LABELS` se queda en el analizador);
  - `incidents/vocabulary.py`: enums y etiquetas de sede del CONTEXT, `TITLE_MAX_LENGTH` = 120;
  - `incidents/rules.py`: `validate_incident_fields` y ciclo de vida;
  - `incidents/csv_mapping.py`: mapeos, título, fecha a medianoche UTC, `customer`/`central`, clave de idempotencia y `prepare_seed_batch` (cargable / inválida / no mapeable / duplicada);
  - `pyproject.toml` y `README.md` propios.
- **`packages/incident-analyzer`:** `schema.py`, `reader.py` y `validation.py` pasan a reexportar desde `nexova_shared`; `__init__.py` añade `packages/shared` a `sys.path` si no está instalado. **Ningún test del analizador se modificó.**
- **Docs:** `AGENTS.md` §4 (fila nueva de `packages/shared`), README del analizador y de `services/api` (instalación con tres paquetes), `services/api/SPECS.md` §1 (dónde viven esquema y reglas), `techContext.md` (inventario, decisión nueva, comando del venv) y `projectbrief.md` (proyecto nuevo, en curso).
- **Corrección del memory-bank:** las menciones de "PR #16 abierta / sin merge" pasan a "integrada en `main`, merge `677e735` (2026-10-07)", y el estado verificado de `origin/main` pasa de `98c8ad2` a `677e735`.
- Sin dependencias nuevas; `services/api/app` y `uis/` no se tocaron.

**Validación ejecutada:**
- Línea base antes del cambio: analizador 118 tests OK (7 skipped: aceptación con el CSV real, ausente); `services/api` 205 OK; `src/` (`npm run check`) 97 OK.
- Después del cambio: analizador 118 OK (7 skipped), igual; `packages/shared` 70 OK (nuevos); `services/api` 205 OK con `nexova_shared` instalado en el venv; `src/` no se tocó.
- Salida de `scripts/analyze.py` idéntica byte a byte antes y después (reporte del fixture de aceptación y del de 13 filas, y `results.csv` exportado).
- `test_contract.py` lee las tablas del CONTEXT; una mutación de prueba (cambiar una etiqueta de sede) lo hace fallar.
- Con el fixture sintético de aceptación: 96 válidas → open 27 / resolved 56 / discarded 13 y technical_failure 49 / process_error 35 / client_complaint 12, como el CONTEXT.

**Pendiente / no verificado:**
- El CSV real (`incidents-nexova.csv`) no está en el checkout: las cifras se verifican con el fixture sintético.
- El fixture no tiene descripciones de más de 120 caracteres; el recorte se cubre con tests unitarios.
- F2–F6 sin empezar en el momento del commit de F1.

---

## 2026-10-06 — AUTH-03: documentación para revisión (guía para el profesor)

**Estado: hecho** (solo documental, sin impacto técnico en el código), sin commit todavía, en la rama `feature/password-reset` (después del commit `cb9d0d5`). Se comiteó en `2a1926a` dentro de la PR #16, integrada en `main` (merge `677e735`, 2026-10-07).

- **`docs/auth-password-reset.md` es ahora el documento principal de AUTH-03.** Se amplía con:
  - endpoints (propósito, autenticación, request, respuesta, errores y seguridad);
  - funcionamiento técnico;
  - sección propia de **H-1** con prueba manual en PowerShell (datos ficticios);
  - puesta en marcha (API con `uv run --env-file .env uvicorn app.main:create_app --factory`, backoffice en 3000 y tracker en 3001);
  - variables de entorno, sin valores;
  - guía de validación manual paso a paso;
  - Resend sin dominio propio (`onboarding@resend.dev` y el destinatario de pruebas `delivered@resend.dev`);
  - resumen de la auditoría de seguridad;
  - comandos exactos de los tests, verificados;
  - estado de la validación manual y deuda técnica.
- **Enlaces añadidos** desde el README de `services/api` y desde `docs/local-development.md`.
- **Referencias corregidas:** "D-PWD-1…11" pasa a "D-PWD-1…12" en el README de la API, `docs/auth-password-reset.md` y `techContext.md`.
- **Validación manual informada por el usuario,** además de la de la entrada de abajo:
  - integración con Resend usando el destinatario de pruebas;
  - H-1 probado a mano: `PUT /users/{id}` con `password` → 403 y la contraseña no cambió;
  - frontend del backoffice;
  - frontend del tracker: `/forgot-password`, envío a Resend, mensaje genérico, botón desactivado tras enviar y `/reset-password`.
- **Comandos de test comprobados al documentarlos:**
  - `test_password_reset.py`: 33 OK;
  - H-1 con `-k`: 6 OK;
  - `password.service.test.mjs` del backoffice: 15 OK;
  - `password.test.mjs` del tracker: 15 OK.

---

## 2026-10-06 — AUTH-03: validación manual con email real, auditoría de seguridad y corrección H-1

**Estado: hecho** en la rama `feature/password-reset`; se comiteó después en `cb9d0d5` (PR #16). Continúa la entrada del 2026-10-05 de abajo.

- **Validación manual del usuario, de extremo a extremo:**
  - `forgot-password` devuelve 200 sin revelar si el usuario existe;
  - el email real llega por Resend;
  - `reset-password` funciona y el token caduca y es de un solo uso (reutilizarlo da error);
  - `change-password` rechaza una contraseña actual incorrecta y funciona con la correcta.
- **Diagnóstico previo:** un `forgot-password` sin email era correcto, porque el email probado no estaba registrado en `services/api/data/auth.json`. La auditoría lo registró como `reset_requested` / `unknown_email` y por diseño no se llama a Resend.
- **Auditoría de seguridad de AUTH-03 (solo lectura):** sin hallazgos CRITICAL y con un HIGH (**H-1**).
  - H-1: `PUT /users/{id}` permitía a un usuario normal cambiar su `password` sin la contraseña actual, esquivando `POST /auth/change-password`. Venía de AUTH-01 (D-AUTH-13).
  - Hallazgos no bloqueantes, **sin corregir**:
    - M-1: restablecer o cambiar la contraseña no cierra las sesiones JWT abiertas;
    - M-2: diferencia de tiempo en `forgot-password` entre email existente y desconocido;
    - M-3: escrituras sin autenticación ni rate limiting en `auth.json`;
    - L-1…L-6: ver la sección "Decisiones y problemas conocidos".
- **H-1 corregido:**
  - `app/routes/users.py`, `update_user`: si quien no es admin envía `password`, responde 403 `forbidden` y no aplica ningún campo de la petición, igual que con `role`;
  - el cambio de contraseña de los usuarios normales va exclusivamente por `POST /auth/change-password`;
  - un admin conserva la capacidad de AUTH-01 de fijar contraseñas con `PUT /users/{id}`.
- **Tests de `tests/test_auth.py`:**
  - el antiguo [18] (`test_user_updates_own_email_and_password`) pasa a ser `test_user_updates_own_email`, porque exigía justo el comportamiento eliminado;
  - 5 tests nuevos: usuario y manager rechazados, cambio de otro usuario rechazado, admin conserva la capacidad, y `change-password` sigue siendo el camino (400 con la actual incorrecta, 200 con la correcta).
- **Resultado:** `services/api` pasa 205 tests (200 + 5).
- **Docs:** D-AUTH-13, §18 y §21 de `services/api/SPECS.md` actualizados; D-PWD-12 y el riesgo residual en §27 nuevos; tabla de endpoints y sección AUTH-03 del README de la API.

**Pendiente:**
- Revisión de P3-1…P3-6 por el tech lead o la CTO.
- Decisión sobre M-1, M-2 y M-3.
- Riesgo residual de H-1 (SPECS §27): un admin puede fijar contraseñas con `PUT /users/{id}` sin la actual, también la suya; ese cambio no invalida enlaces de reset pendientes ni queda en `password_audit`.
- ~~Commit y PR~~: hecho, commit `cb9d0d5` y PR #16, integrada en `main` (merge `677e735`, 2026-10-07).

---

## 2026-10-05 — AUTH-03: recuperación y cambio de contraseña (`services/api`, `uis/backoffice`, `uis/talent-pipeline-tracker`)

**Estado: hecho y validado automáticamente; validación manual con email real completada el 2026-10-06 (entrada de arriba).** Rama `feature/password-reset` (creada desde `main` en `87a7047`, merge de la PR #15), sin commit todavía. Contexto: ticket AUTH-03 ([`docs/auth-password-reset.md`](../docs/auth-password-reset.md)); contrato en `services/api/SPECS.md` Parte D.

**Decisiones del usuario:** Resend como proveedor, llamado por HTTP con la librería estándar (sin dependencias nuevas); flujos en backoffice y tracker; de los opcionales, solo la auditoría. Las decisiones técnicas son D-PWD-1…11 (SPECS §24); las decisiones de implementación que el ticket no fija son **propuestas pendientes de revisión** P3-1…P3-6 (`docs/auth-password-reset.md` §4).

**Qué se hizo:**
- **`services/api`:** `POST /auth/forgot-password` (siempre 200 con el mismo cuerpo; email en segundo plano), `POST /auth/reset-password` (400 `invalid_reset_token`), `POST /auth/change-password` (protegido; 400 `incorrect_password`). Token opaco de 256 bits guardado solo como SHA-256 en la tabla `password_reset_tokens` de `auth.json`, vigencia 15–60 min (30 por defecto), un solo uso. Auditoría en `password_audit` (evento, `user_id`, IP, motivo, fecha; sin email ni token). Envío con `app/auth/email.py` (Resend por `urllib`). Nuevas variables `RESEND_API_KEY`, `EMAIL_FROM`, `PASSWORD_RESET_URL` (todas o ninguna) y `PASSWORD_RESET_TOKEN_EXPIRE_MINUTES`; `.env.example` y README actualizados.
- **Backoffice y tracker:** `/forgot-password` (pública), `/reset-password` (abierta, con o sin sesión), `/account/change-password` (protegida), enlace "¿Olvidaste tu contraseña?" en `/login`, aviso tras `?reset=success` y enlace a cambiar contraseña desde el perfil. Sin dependencias nuevas.
- **Docs:** `docs/auth-password-reset.md` (nuevo); `services/api/SPECS.md` Parte D; READMEs de API, backoffice y tracker; `SPECS.md` §9.4, `CLAUDE.md` de las dos apps; `docs/local-development.md`; `AGENTS.md` §4; `uis/README*.md`; `.agents/rules/app-specific-overrides.md`; `techContext.md`.

**Validación ejecutada:**
- `services/api`: 200 tests OK (167 anteriores + 33 nuevos en `tests/test_password_reset.py`; ninguno llama a Resend). Prueba de humo contra un uvicorn real (puerto 8010, base temporal fuera del repo): 18/18, incluido el preflight CORS desde 3000 y 3001 de las tres rutas.
- `uis/backoffice`: `tsc`, `lint` y `build` OK (rutas nuevas estáticas); 263 tests OK (240 + 23 nuevos en `tests/password.service.test.mjs`; ajustados los tests de rutas y el estático de producción).
- `uis/talent-pipeline-tracker`: `tsc` y `build` OK; 35 tests OK (20 + 15 en `tests/password.test.mjs`); `lint` solo con los 4 errores preexistentes.
- Navegador (servidores de desarrollo del usuario, sin enviar formularios): enlace en `/login` de las dos apps, `/forgot-password`, `/reset-password` sin token (error y enlace) y con token (formulario; el token desaparece de la URL; `referrer: no-referrer`), aviso en `/login?reset=success`. Sin errores de consola.

**Pendiente / no verificado:**
- ~~Email real con Resend~~ y ~~flujo completo en el navegador contra la API nueva~~: **hechos el 2026-10-06** (entrada de arriba).
- Revisión de P3-1…P3-6 por el tech lead o la CTO.
- Fuera de alcance (SPECS §27): cerrar sesiones abiertas al cambiar la contraseña, rate limiting, plantilla HTML, retención de la auditoría.

---

## 2026-10-05 — Validación manual de la exportación autenticada de `/incidents` y deuda de `LastResultStore`

**Estado: hecho** (solo documental, sin impacto técnico en el código). Se registra la validación manual del usuario en el navegador (backoffice en `http://localhost:3000`, API en `http://localhost:8000`): la exportación de `/incidents` con token funciona y una sesión inválida durante la exportación lleva a `/login` (detalle en la entrada de AUTH-02, "Validación ejecutada"). Se retira ese pendiente de AUTH-02. Se registra también como deuda pendiente, **sin corregir**, que `LastResultStore` es global al proceso y no por usuario (ver "Decisiones y problemas conocidos"). Rama `docs/auth02-export-validation`, creada desde `main` en `98c8ad2` (merge de la PR #14).

---

## 2026-10-05 — Memory-bank tras el merge de AUTH-02 (PR #13)

**Estado: hecho** (solo documental, sin impacto técnico en el código). AUTH-02 se integró en `main` con la PR #13 (commit `e2d4cbd`, merge `a4b6369`, 2026-10-05; `git diff e2d4cbd a4b6369` vacío). Se corrigen las menciones de "PR abierto" / "no está en `main`" en `techContext.md` y en la entrada de AUTH-02 de abajo, se retira el pendiente "merge del PR" y se actualiza el próximo paso de AUTH-01 (enviar el token desde el backoffice ya lo resolvió AUTH-02). `docs/auth-frontend.md` §3 deja constancia de que el merge **no** aprueba P-1…P-7: siguen pendientes de revisión del tech lead o la CTO. Rama `chore/memory-bank-auth-frontend-merged`, creada desde `main` en `a4b6369`.

---

## 2026-10-02 / 2026-10-05 — AUTH-02: autenticación en el frontend (`uis/backoffice`, `uis/talent-pipeline-tracker`, CORS de `services/api`)

**Estado: hecho, validado (automático y manual) e integrado en `main`** con la PR #13 (rama `feature/auth-frontend`, creada desde `main` en `7815e26`; commit `e2d4cbd`, merge `a4b6369`, 2026-10-05). Pendiente: revisión de P-1…P-7 por el tech lead o la CTO (el merge no las aprueba). `docs/auth-frontend.md` separa requisitos del ticket, hechos comprobados y **propuestas pendientes de revisión** (P-1…P-7: puerto 3001, `NEXT_PUBLIC_AUTH_API_URL`, validación con `GET /auth/me`, `null` en el perfil, CORS, destino tras login y email en cabecera, sin refresh tokens); ninguna está aprobada por el tech lead ni por la CTO.

**Estado real tras AUTH-02 (hechos comprobados):**
- AUTH-01 (backend) ya existía: `services/api` emite el JWT y lo exige en incidentes, proveedores, `/users`, `/auth/me` y `/profiles/me`.
- Backoffice y tracker integran login, registro, perfil y logout; todas sus vistas salvo `/login` y `/register` exigen sesión mediante un guard en cliente en el layout raíz (sin middleware de Next.js y sin cookies).
- JWT en `localStorage` (`nexova.backoffice.access_token` / `nexova.tracker.access_token`); `Authorization: Bearer` solo en `lib/api-client.ts` de cada app. Un 401 borra el token y lleva a `/login`. Sin refresh tokens.
- Contrato usado: `POST /auth/login` con `application/x-www-form-urlencoded` (`username` = email); `POST /users` sin `role`; `GET /auth/me` valida la sesión (una vez por token); `PUT /profiles/me` edita nombre, teléfono y dirección (`null` borra el dato).
- Tracker: `NEXT_PUBLIC_AUTH_API_URL` apunta a `services/api`; `NEXT_PUBLIC_API_URL` sigue siendo la API de 4Geeks, que **nunca** recibe el JWT. Puerto 3001.
- CORS: la API permite `PUT`; en desarrollo `CORS_ALLOWED_ORIGINS` debe incluir `http://localhost:3001` (documentado en `services/api/.env.example`); el `.env` local con los valores reales **no se versiona**.
- `uis/website` sigue público, sin cambios y fuera del sistema de autenticación.
- Guía de arranque del sistema completo: [`docs/local-development.md`](../docs/local-development.md) (nueva, 2026-10-05).

Contexto: ticket AUTH-02 ([`docs/auth-frontend.md`](../docs/auth-frontend.md)): la API ya exige JWT (AUTH-01) y el frontend debe hacer login/registro, guardar el token en `localStorage`, enviarlo como `Authorization: Bearer`, tener página de perfil y proteger todas las vistas de las apps del monorepo salvo el website público. Termina la rotura temporal de `/incidents` y `/suppliers` (401) de AUTH-01.

**Qué se hizo:**
- **Backoffice:** `/login`, `/register` (`POST /users` + `POST /auth/login`), `/account/profile` (`GET /auth/me` + `PUT /profiles/me`); guard global y sesión en el layout raíz; cabecera con perfil, email y "Cerrar sesión"; cliente HTTP con Bearer y 401 centralizados; `session_expired` en los errores de incidentes y proveedores.
- **Tracker:** mismos flujos contra `services/api` (`authApiClient`); la API de 4Geeks no recibe el token; cabecera nueva; puerto 3001; variable `NEXT_PUBLIC_AUTH_API_URL`.
- **`services/api`:** CORS permite `PUT`; `.env.example` añade el origen `http://localhost:3001`; test de CORS actualizado (+1 test de preflight `PUT /profiles/me`).
- **Docs:** `docs/auth-frontend.md` y `docs/local-development.md` (nuevos); `uis/README.md`/`README.es.md` (estado de las apps y enlace a la guía); `CLAUDE.md`/`README.md` del backoffice; `SPECS.md` §9, `CLAUDE.md` y `README.md` del tracker; `SPECS.md` (D-AUTH-12, §22), `README.md` y `.env.example` de `services/api`; `AGENTS.md` §4; `.agents/rules/app-specific-overrides.md`; `techContext.md`.

**Validación ejecutada:**
- `uis/backoffice`: `tsc`, `lint` y `build` OK (rutas nuevas `/login`, `/register`, `/account/profile`); 240 tests OK (172 anteriores + 68 nuevos). Dos tests existentes ajustados porque el contrato cambió a propósito: el 401 de una petición protegida ya no llega al servicio (se mantiene la comprobación de que no se filtra el cuerpo).
- `uis/talent-pipeline-tracker`: `tsc` y `build` OK; 20 tests nuevos OK (3 de ellos, 2026-10-05, cubren el flujo login → token → `/auth/me` y el caso de respuesta bloqueada por CORS); `lint` con 4 errores `react-hooks/set-state-in-effect` **anteriores** a AUTH-02 (`use-notes`, `use-record-detail`, `use-records`, sin cambios en esta rama).
- `services/api`: 167 tests OK (166 anteriores + 1 nuevo de preflight `PUT`).
- `src/` 97 tests OK y `packages/incident-analyzer` 118 OK (7 omitidos), sin cambios en esta rama.
- Validación manual del usuario (2026-10-05): backoffice (login correcto e incorrecto, registro, perfil GET/PUT, logout, protección de rutas, botón atrás tras logout, token inválido/401); tracker (protección de `/`, login, JWT en `localStorage`, acceso autenticado, candidaturas de 4Geeks); website como HTML estático público.
- Navegador, con la API real (uvicorn, TinyDB temporal fuera del repo, orígenes 3000 y 3001): sin token → `/login`; registro con 422 por campo y después correcto (token + `/`); `/suppliers` (15 filas) e `/incidents` (análisis del CSV sintético) con Bearer; perfil leído y editado con `PUT /profiles/me`; token inválido → 401 → token borrado y `/login`; login incorrecto → mensaje y sin token; `/login` con sesión → `/`; logout → `/login` y vistas protegidas inaccesibles. Tracker: `/` sin sesión → `/login` sin llamar a 4Geeks, login incorrecto/correcto, listado de candidaturas, perfil (borrar teléfono → `null`), logout y `/candidates/[id]` protegido.
- Exportación autenticada de `/incidents` (validación manual del usuario, 2026-10-05, tras el merge): con sesión válida, análisis de `packages/incident-analyzer/tests/fixtures/incidents-acceptance-synthetic.csv` → "Exportar" → `GET /api/incidents/results/export` 200 → descarga de `results.csv` con `total_records,100`, `valid_records,96`, `invalid_records,4` y `satisfaction_average_score,3.84` (las cifras de `docs/COMPANY_INCIDENT_FILE_ANALIZER_PROJECT.md`, que el fixture sintético reproduce; no es una verificación con el CSV real). Con `nexova.backoffice.access_token` sustituido por un valor inválido, la exportación detecta la sesión inválida y la app cierra la sesión y redirige a `/login`.

**Pendiente / no verificado / problemas preexistentes:**
- Revisión de las propuestas P-1…P-7 por el tech lead o la CTO: siguen pendientes después del merge.
- Preexistente (también en `main`): 4 errores de lint `react-hooks/set-state-in-effect` en el tracker (`use-notes.ts:63`, `use-record-detail.ts:58`, `use-records.ts:75` y `:112`); AUTH-02 no los introduce ni los corrige.
- Preexistente: `npx tsc --noEmit` en las apps Next.js falla sin `.next/` (`LayoutProps`/`PageProps` los genera Next); ejecutar antes `npm run build`.
- Registro desde la UI del tracker (mismo servicio y flujo probados en tests y en el backoffice).
- Quien tenga un `services/api/.env` anterior debe añadir `http://localhost:3001` a `CORS_ALLOWED_ORIGINS` para usar el tracker, y el `.env.local` del tracker necesita `NEXT_PUBLIC_AUTH_API_URL`.
  *Confirmado el 2026-10-05:* con el `.env` local solo en `http://localhost:3000`, el login del tracker devolvía 200 en la red pero el navegador bloqueaba la respuesta (petición CORS simple, sin preflight): `fetch` fallaba, el tracker mostraba "No se pudo conectar con el servidor" y no se guardaba el token. Corregido en el `.env` local (no versionado); `tests/auth.test.mjs` del tracker cubre ahora ese caso y el flujo login → token → `/auth/me` → vista autenticada.
- Sin refresh tokens: al expirar el JWT se vuelve a `/login` (fuera de alcance, igual que en AUTH-01).

---

## 2026-09-30 — README de `services/api`: tests con uv y sincronización del venv

**Estado: hecho** (solo documental, sin impacto en el código). El README decía que `uv run` conserva siempre el núcleo `incident-analyzer` instalado con pip, pero `uv run --extra dev …` lo desinstaló al sincronizar el `.venv`. Se corrige la sección del seeder (qué comandos lo conservaron, `--no-sync` y cómo reinstalarlo) y se añade a la sección de tests el comando con uv (`uv run --no-sync python -m unittest discover -s tests -t .`) y la aclaración de que no hay pytest (D-API-3). Mismo ajuste en `techContext.md`. Rama `docs/api-readme-uv-tests`, creada desde `chore/memory-bank-auth-merged` (PR #11) para no chocar en `progress.md`.

---

## 2026-09-30 — Repositorio renombrado a `nexova-platform` y memory-bank tras el merge de AUTH-01

**Estado: hecho** (solo documental, sin impacto técnico en el código). El repositorio de GitHub pasa de `Milestone-0-Elige-tu-empresa` a `nexova-platform` (detalle en `techContext.md`, "Estado real en `main`"); ningún archivo versionado citaba el nombre antiguo. Se actualizan las menciones de AUTH-01 de "pendiente de merge" a integrado con el PR #10. Rama `chore/memory-bank-auth-merged`, creada desde `main` en `09b86f1`.

---

## 2026-09-30 — AUTH-01: autenticación JWT y protección de rutas (`services/api`)

**Estado: hecho — validado por el tech lead (pruebas en `/docs` y desde el origen del backoffice) y commiteado en la rama `feature/auth-api`** (creada desde `api-con-almacenamiento-ligero` en `9988355`, mismo árbol que el merge del PR #9 en `main`). Integrado en `main` con el PR #10 (mergeado el 2026-09-30 21:50 UTC, merge `09b86f1`). El frontend queda fuera de alcance por el propio ticket (se actualizará para enviar el token en una fase posterior).

Contexto: ticket AUTH-01 (`docs/auth-api.md`): la CTO exige que ninguna ruta que modifique o exponga datos sensibles sea accesible sin sesión válida. Decisiones D-AUTH-1…13 en `services/api/SPECS.md` Parte C (§15–§22), fijadas por el tech lead el 2026-09-30.

**Qué se hizo:** paquete `app/auth/` (modelos `User`/`Profile`, `AuthRepository` TinyDB en `AUTH_DB_PATH` con ids UUID, bcrypt con libpass, JWT HS256 con python-jose, `UserService`, `get_current_user`/`require_admin`/`ensure_self_or_admin`, comando `uv run create-admin`); rutas `app/routes/{auth,users,profiles}.py`; las 8 rutas existentes (6 de `/suppliers`, 2 de `/api/incidents`) protegidas a nivel de router; `JWT_SECRET_KEY` (≥ 32 caracteres) y `ACCESS_TOKEN_EXPIRE_MINUTES` obligatorias al arrancar (sin valor por defecto); CORS `allow_headers=["Authorization"]`.
**Archivos añadidos:** `docs/auth-api.md`; `services/api/app/auth/{__init__,models,repository,security,service,dependencies,create_admin}.py`; `services/api/app/routes/{auth,users,profiles}.py`; `services/api/tests/{auth_support,test_auth,test_auth_protection,test_create_admin}.py`.
**Archivos modificados:** `services/api/{app/main.py,app/core/config.py,app/core/errors.py,pyproject.toml,uv.lock,.env.example,README.md,SPECS.md}`; `services/api/tests/{support,suppliers_support,test_architecture}.py` (clientes de test con JWT válido; excepción documentada de `"@"` y `print`); `.gitignore` (`.env.*` salvo `.env.example`); `AGENTS.md` §4; `services/README*.md`; `memory-bank/{progress,techContext}.md`.
**Dependencias:** `libpass[bcrypt]>=1.9.3,<1.10` (bcrypt 5.0.0) y `python-jose[cryptography]>=3.5,<3.6` (3.5.0; arrastra ecdsa, rsa, pyasn1, six y, por el extra, cryptography 50.0.2, cffi, pycparser), autorizadas por el ticket.

**Validación ejecutada:**
- Revisión final (tech lead): `POST /users` ya no acepta `role` (`UserCreate` = `email`, `password`, `name`, `phone`, `address`; `role` → 422) y el backend fija siempre `user`; antes aceptaba `role` y respondía 403 a `admin`/`manager` (no lo exigía ningún contrato). CORS, refresh/revocación de tokens: sin cambios, documentados como fuera de alcance (`SPECS.md` §22).
- `services/api`: 166 tests OK (109 anteriores + 57 de AUTH-01). Mutaciones detectadas: quitar la protección de `/suppliers` (20 fallos) y quitar el control de `role` en `PUT /users/{id}` (4 fallos).
- `packages/incident-analyzer`: sin cambios; ver la validación en el resumen de la tarea.
- Manual con uvicorn real y TinyDB temporal: sin `JWT_SECRET_KEY` la app no arranca (`ConfigError`); flujo registro → login → 401 sin token / token inválido → 200 con token en proveedores e incidentes → `/auth/me` y `/profiles/me` → 403 de A sobre B y al autoelevarse → `create-admin` → admin lista, cambia rol y borra (perfil borrado): 24/24. En `/docs`, el botón *Authorize* hace login en `/auth/login` y `GET /auth/me` responde 200; Swagger marca 15 operaciones protegidas.
- Incidencia durante la validación manual: un `.env` con rutas Windows con `\` no lo interpretó `uv`, y la API usó `services/api/data/` (se añadió un proveedor de prueba y se creó `data/auth.json`); ambos se revirtieron y `.env.example` documenta usar `/` en rutas.

**Pendiente:**
- ~~Revisión del tech lead, commit, PR contra `main` y merge~~ — hecho (PR #10).
- Para ejecutar los tests con uv, desde `services/api`: `uv run --no-sync python -m unittest discover -s tests -t .` (no hay pytest: D-API-3). Sin `--no-sync`, `uv run --extra dev` sincroniza el `.venv` y desinstala el núcleo `incident-analyzer` instalado con pip (se reinstala con `pip install --no-deps -e packages/incident-analyzer`). ~~El README de `services/api` aún dice que `uv run` lo conserva~~ — corregido (entrada "README de `services/api`: tests con uv", 2026-09-30).
- ~~CORS no incluye `PUT`~~ — añadido en AUTH-02 (entrada 2026-10-02).
- ~~El backoffice (`/suppliers`, `/incidents`) responde 401 hasta que envíe el token~~ — resuelto en AUTH-02 (entrada 2026-10-02).
- Sin revocación/refresh de tokens ni forma de desactivar usuarios por API; nada impide que el último admin se degrade o se borre (se recupera con `create-admin`).

---

## 2026-09-29 — Directorio de proveedores: API TinyDB (`services/api`) + vista `/suppliers` (`uis/backoffice`)

**Estado: hecho — revisado por el tech lead y commiteado en la rama `api-con-almacenamiento-ligero` (creada desde `main` tras el PR #7, con `main` fusionado después para incorporar el PR #8). Integrado en `main` con el PR #9 (mergeado el 2026-09-28 23:53 UTC).**

Contexto: `docs/ligthweight-storage-api.md` (Patricia Solís, HR Manager; tech lead Sergio Molina). Sustituir la hoja de cálculo de proveedores por una API con fuente de verdad única. Decisiones D-SUP-1…12 en `services/api/SPECS.md` Parte B (incluida la tensión `DELETE` ↔ suspensión controlada, §10).

**Archivos añadidos:** `docs/ligthweight-storage-api.md` (contexto; solo se actualizaron las 2 líneas de cabecera que citaban el nombre y la ruta antiguos); `services/api/app/{models,database,seed}.py`, `services/api/app/routes/{__init__,suppliers}.py`, `services/api/tests/{suppliers_support,test_suppliers_api,test_suppliers_seed}.py`, `services/api/uv.lock`; `uis/backoffice/app/suppliers/page.tsx`, `components/suppliers/*`, `hooks/use-supplier-directory.ts`, `services/suppliers.service.ts`, `lib/supplier-renewal.ts`, `types/suppliers.ts`, `tests/{suppliers-contract,suppliers.service,use-supplier-directory}.test.mjs`, `tests/support/supplier-fakes.mjs`.
**Archivos modificados:** `services/api/{app/main.py,app/core/config.py,app/core/errors.py,pyproject.toml,README.md,SPECS.md,.env.example,tests/test_architecture.py,tests/test_errors.py}`; `uis/backoffice/{app/layout.tsx,lib/api-client.ts,services/normalizers.ts,tests/production-source.test.mjs,CLAUDE.md,README.md}`; `.gitignore` (`services/api/data/`); `AGENTS.md` §4; `.agents/rules/app-specific-overrides.md`; `services/README*.md`, `uis/README*.md`; `memory-bank/*`.
**Dependencias:** solo `tinydb` (autorizada). Herramienta: uv (instalada en la máquina, no es dependencia del proyecto).

**Validación ejecutada:**
- `services/api`: 109 tests OK (70 de incidentes + 39 de proveedores). `uv run seed` → 15 insertados; segunda ejecución → 0 (también en una copia limpia sin venv).
- `uis/backoffice`: `tsc`, `lint`, `build` (rutas `/`, `/incidents`, `/suppliers`) y 172 tests Node 24 OK. Mutaciones detectadas por los tests (recarga tras cambio de tarifa, 422 por campo).
- Manual en navegador con la API y TinyDB reales: filtros combinados, tarifa 0 bloqueada y 900 guardada con `updated_at` nuevo, suspender sin tocar `updated_at`, alta vacía sin petición, 422 de moneda incoherente, alta con renovación a 20 días destacada, 375 px sin desbordamiento.

**Pendiente:**
- Adjuntar al PR #9 las 3 capturas que pide el brief (`uv run seed`, un filtro en Swagger y el listado filtrado en la UI) — el checklist del PR seguía sin marcar al mergearse. ~~Hacer el merge~~ — hecho el 2026-09-28.
- Desde AUTH-01 (entrada 2026-09-30), `/suppliers` exige JWT; ~~la vista del backoffice recibe 401~~ — resuelto en AUTH-02 (entrada 2026-10-02).
- Ningún proveedor del seed cae en la ventana de 60 días (todas sus fechas ya pasaron): para la demo hay que registrar uno con fecha próxima.
- El 422 de moneda incoherente es un error del proveedor completo (`loc` = `["body"]`): se muestra en el resumen, no marcado en el campo Moneda.

---

## 2026-09-28 — Revisión del memory-bank y de las reglas de agente (sin impacto técnico)

**Estado: hecho** (solo documental: `memory-bank/`, `AGENTS.md`, `CLAUDE.md`, `.agents/`). Se corrigieron afirmaciones desfasadas tras los PRs #4–#7:
- `projectbrief.md`: ya no dice ser el único contexto de negocio versionado (el `README.md` raíz contiene el briefing desde `6807f5e`); la regla de trazabilidad admite también el `README.md` raíz y los documentos de contexto versionados en `docs/`.
- `techContext.md`: "Estado real en `main`" actualizado a PRs #1–#7; origen del backoffice con fecha/PR en vez de "este cambio"; nota del 2026-09-20 marcada como histórica; inventario de `skills/` y `agents/` completado.
- Este archivo: la entrada del fixture sintético indica su merge (PR #7).
- `AGENTS.md` §3 y `.agents/skills/memory-bank-sync/SKILL.md`: la sincronización del memory-bank ya no depende de que haya commit — se aplica al cerrar cualquier tarea que modifique archivos (`progress.md` siempre, `techContext.md`/`projectbrief.md` solo si procede); las tareas de solo lectura no la disparan. Corregida la referencia "`AGENTS.md` (§5)" de la skill (es §4, paso 4). Motivo: una sesión que editaba archivos sin comitear dejaba el memory-bank desfasado.
- `CLAUDE.md` raíz nuevo, con solo `@AGENTS.md`: garantiza que Claude Code cargue `AGENTS.md` en cada sesión sin depender de que lo detecte por su cuenta, y sin duplicar su contenido (mismo patrón que `uis/talent-pipeline-tracker/CLAUDE.md`).

**Verificado al revisar:** núcleo 118 tests OK (7 skipped), API 70 OK, 97 tests en `src/`, versiones de Next/React en ambos `package.json`.

- Resuelto el "Pendiente derivado" de la entrada 2026-09-27: `AGENTS.md` (§1, §3 y §4.3), `.agents/rules/monorepo-structure.md`, `.agents/rules/nexova-context.md` y la skill `memory-bank-sync` ya no remiten a la guía de carpetas del `README.md` raíz ni tratan `projectbrief.md` como única referencia versionada. La convención de carpetas vigente es la tabla de `monorepo-structure.md` (la guía original sigue en `git show fda5125:README.es.md`); las fuentes de negocio son `contexts/CONTEXT.md`, su copia en el `README.md` raíz, los `contexts/hitoN/*.md`, los documentos de contexto de `docs/` y `projectbrief.md`.

---

## 2026-09-27 — Procesador de incidentes: fixture sintético de aceptación

**Estado: hecho, integrado en `main` con el PR #7.** `packages/incident-analyzer/tests/fixtures/incidents-acceptance-synthetic.csv` (100 filas sintéticas, emails `example.invalid`) reproduce exactamente las cifras de `docs/COMPANY_INCIDENT_FILE_ANALIZER_PROJECT.md` (100/96/4, categorías, estados, satisfacción, media 3.84); lo verifica `tests/test_acceptance_synthetic.py`, que se ejecuta siempre. Documentado en `tests/fixtures/README.md` y en el `README.md` del paquete. **No sustituye** al test con el CSV real (`test_acceptance.py`), que sigue omitido.

**Validación:** `python -m unittest discover -s packages/incident-analyzer/tests -t packages/incident-analyzer` → 118 tests OK (7 skipped: aceptación con el CSV real).

---

## 2026-09-27 — `README.md` raíz sustituido por el briefing de Nexova

**Estado: hecho** (cambio del usuario, solo documental). El `README.md` raíz deja de ser la guía de la plantilla de 4Geeks y pasa a ser el briefing de empresa de Nexova (contenido idéntico a `contexts/CONTEXT.md`); se elimina `README.es.md`. Consecuencia: el briefing general ya viaja con el repositorio; `contexts/` sigue ignorado.

**~~Pendiente derivado~~ — resuelto el 2026-09-28 (ver entrada de arriba):** `AGENTS.md` §3 y `.agents/rules/monorepo-structure.md` / `nexova-context.md` aún citan la convención de carpetas o el `CONTEXT.md` "descrito en `README.md` raíz"; la convención sigue en `.agents/rules/monorepo-structure.md` y en el historial (`git show fda5125:README.es.md`).

---

## 2026-09-23 — Procesador de reportes de incidentes, Fase 3: UI `/incidents` en `uis/backoffice`

**Estado: hecha — implementada, validada (pasos 1–6) y aprobada por el tech lead; commiteada en la rama `feature/incident-analyzer` con el mensaje `feat(backoffice): implementa la vista /incidents para el análisis de incidentes Nexova`, sobre la Fase 2 (`4120de5`). Integrada en `main` con el PR #6 (mergeado el 2026-09-23).** Fase 4 (integración) no iniciada.

Contexto: vista web para que Atención al Cliente suba el CSV, vea las métricas y descargue `results.csv`, consumiendo la API de la Fase 2. La UI es decisión del tech lead (H1–H12): el documento de contexto de Nexova describe un script, no una interfaz.

**Pasos:**
1. Preparación: `uis/backoffice/CLAUDE.md` y `README.md` autorizan `/incidents`; `.gitignore` con `!.env.example`; `.env.example` (`NEXT_PUBLIC_API_URL`); tokens semánticos en `globals.css`.
2. Tipos (`types/incidents.ts`) y normalizador (`services/normalizers.ts`, única frontera con `unknown`, whitelist).
3. Cliente HTTP genérico (`lib/api-client.ts`, sin `unknown`: JSON tipado como `JsonValue`) y servicio (`services/incidents.service.ts`).
4. Hook `hooks/use-incident-analysis.ts` (reducer + sesión: cancelación, carreras, exportación ligada al `analysis_id` mostrado).
5. UI: `app/incidents/page.tsx` (Server Component) + `components/incidents/*` + primitivas `components/ui/*` (incl. `nav-link.tsx`) + enlace en la cabecera de `app/layout.tsx`. La portada `app/page.tsx` no cambia.
6. Validación manual en navegador, documentación (`uis/backoffice/README.md`, `CLAUDE.md`, `AGENTS.md` §4, `uis/README*.md`) y este Memory Bank.

**Validación ejecutada:**
- `uis/backoffice`: `npx tsc --noEmit`, `npm run lint`, `npm run build` (rutas `/`, `/_not-found`, `/incidents`, sin `.env.local`) y tests Node 24 (`node --disable-warning=MODULE_TYPELESS_PACKAGE_JSON --import ./tests/support/resolve-alias.mjs --test --test-timeout=10000 "tests/*.test.mjs"`) → 115 tests OK. Mutaciones sobre copias en scratchpad detectadas por los tests (privacidad de errores, `unknown`/`any`, carreras del hook, Blob en estado…).
- Manual en navegador, con API local propia y fixture sintético (`example.invalid`), instrumentando `fetch` y `<a>.click()` solo en la página de prueba (sin tocar producción): (A) la descarga se inicia como `results.csv`, contenido `metric,value` que coincide con el análisis mostrado (13 registros, media 3.75), sin `@`, `customer_email` ni datos de filas — el panel del navegador integrado no guarda el archivo en disco, así que el contenido se verificó leyendo el Blob desde el instrumental; (B1) export de A pendiente + análisis B correcto → export abortado, ninguna descarga, se muestra B; (B2) export de A pendiente + B falla → A sigue visible y su export termina y descarga A; (C) salir de `/incidents` con un análisis pendiente → petición abortada antes de enviarse, sin error visible ni descarga. 360 px sin desbordamiento; peticiones solo a `localhost`.
- Hallazgos corregidos durante la validación: botón secundario sin borde visible (clases de color de borde en conflicto) y un segundo landmark `banner` en `/incidents`.

**Pendiente:**
- ~~Push de la rama y PR contra `main`~~ — hecho: PR #6, mergeado el 2026-09-23.
- Fase 4 (integración) no iniciada.
- Test de aceptación con el CSV real (las cifras 100/96/4 siguen sin verificar con datos reales).
- `UiError` no tiene un caso "sin archivo": `analyze()` sin archivo usa `request_invalid` (la UI deshabilita el botón, así que no se alcanza).
- El texto "aproximadamente 1 MiB" de la UI es copy de UX: si se cambia `MAX_UPLOAD_BYTES` en el servidor, hay que actualizarlo (el 413 sigue siendo la fuente de verdad).

---

## 2026-09-23 — Procesador de reportes de incidentes, Fase 2: API HTTP (`services/api/`)

**Estado: hecha — implementada, validada y aprobada por el tech lead tras la code review (veredicto `APROBABLE SIN CAMBIOS`); commiteada en la rama `feature/incident-analyzer` con el mensaje `feat(api): implementa API FastAPI para análisis de incidentes Nexova`, sobre la Fase 1 (`0203023`). Integrada en `main` con el PR #6 (mergeado el 2026-09-23).** Estado de la Fase 3: ver la entrada de arriba.

Contexto: exponer por HTTP el mismo análisis que la CLI para que el backoffice (Fase 3) pueda subir el CSV y descargar la exportación. Diseño aprobado por el tech lead con las decisiones D-API-1…11 (registradas en `services/api/SPECS.md` §2 y en `techContext.md`).

**Contrato:** `POST /api/incidents/analyze` (multipart, campo `file`, `.csv`) → JSON con `analysis_id`, `analyzed_at`, totales, 7 reglas, 5 categorías, 3 estados, satisfacción (decimales como string) e info de exportación; `GET /api/incidents/results/export` → `results.csv` (`metric,value`) del último análisis que terminó correctamente, con `X-Analysis-Id`, 404 `no_analysis` si no hay; ambas respuestas 200 con `Cache-Control: no-store`; `GET /health`. **Procedencia:** las rutas son decisión del tech lead, no del documento de contexto de Nexova (que no define ninguna API).

**Correcciones tras la code review (2026-09-23):**
- El núcleo local ya **no** se declara como dependencia en `services/api/pyproject.toml` (nombre libre en PyPI → riesgo de *dependency confusion*); se instala junto al servicio con `pip install -e packages/incident-analyzer -e "services/api[dev]"` (verificado con un venv recreado desde cero).
- Rangos acotados a lo probado: `fastapi>=0.141,<0.142`, `python-multipart>=0.0.32,<0.1`, `uvicorn>=0.53,<0.54`, `httpx>=0.28,<0.29` (sin lockfile).
- `MAX_UPLOAD_BYTES` (1 MiB) documentado como límite del **body HTTP completo**, no del CSV.
- El handler genérico de `HTTPException` conserva las cabeceras de la excepción: el 405 incluye `Allow`.
- `Cache-Control: no-store` en análisis y exportación.
- Semántica documentada: se guarda "el último análisis que termina correctamente" (sin cambiar la implementación).
- Comando de la suite de la API explícito con el Python del venv (`AGENTS.md` §4 y README); `.agents/rules/app-specific-overrides.md` lista la documentación local de `services/api` y `packages/incident-analyzer`.
- 9 tests nuevos: frontera exacta del body (`MAX` → 200, `MAX+1` → 413, con y sin `Content-Length`), ausencia de volcado a disco (espía de `SpooledTemporaryFile.rollover` + control positivo), A correcto + B fallido por 413 y por 500 → el export sigue siendo A, `Allow` en 405, `Cache-Control` en POST y export.

**Archivos añadidos:** `services/api/` (`README.md`, `SPECS.md`, `.env.example`, `pyproject.toml`, `app/{main,core/{config,errors,limits},modules/incidents/{router,schemas,service,store}}.py` + `__init__.py`, `tests/` con 5 módulos + `support.py`); `packages/incident-analyzer/tests/test_binary_stream.py`.
**Archivos modificados:** `packages/incident-analyzer/incident_analyzer/{analyze,__init__}.py` (nueva `analyze_binary_stream`, D-API-9) y su `README.md`; `.gitignore` (`.venv/`, `*.egg-info/`); `AGENTS.md` §4 (comando de la API con el venv, se mantiene el de la Fase 1); `.agents/rules/app-specific-overrides.md` (tabla de documentación local); `services/README.md` + `README.es.md` (catálogo de servicios); `memory-bank/{progress,techContext,projectbrief}.md`.
**Sin cambios:** `uis/*`, `src/`, `scripts/analyze.py`. Dependencias nuevas solo en `services/api` (las autorizadas: fastapi, python-multipart, uvicorn, httpx).

**Validación ejecutada:**
- Núcleo: `python -m unittest discover -s packages/incident-analyzer/tests -t packages/incident-analyzer` → 106 tests, 99 OK + 7 skipped (aceptación con CSV real, sigue PENDIENTE).
- API: `services\api\.venv\Scripts\python -m unittest discover -s services/api/tests -t services/api` → 70 tests OK.
- `pip check` en el venv: sin requisitos rotos. `git diff --check`: limpio.
- Comprobaciones manuales: arranque real con `uvicorn app.main:create_app --factory --workers 1` (health, analyze, export; 413 con 2 MiB, 20 MiB y chunked; el access log no contiene emails); los tests clave detectan fallos si se revierte la corrección (literal de categoría → `test_architecture`; sin middleware de 500 → tests de excepción; sin cabeceras → test de `Allow`; sin `no-store` → tests de caché).

**Pendiente:**
- ~~Push de la rama y PR contra `main`~~ — hecho: PR #6, mergeado el 2026-09-23.
- Fuera de alcance por decisión del tech lead (no corregidos): códigos HTTP no estándar en el handler genérico, `filename=""` (responde 422), nombre de paquete genérico `app`, migración a `httpx2`, lockfile, `/api/v1`.
- ~~Fase 3 (frontend en `uis/backoffice`) y Fase 4 (integración): no iniciadas~~ — corregido: la Fase 3 se implementó, validó y commiteó el 2026-09-23 (entrada de arriba); la Fase 4 sigue sin iniciar.
- Test de aceptación con el CSV real (igual que en la Fase 1).
- `docs/ARCHITECTURE_PROPOSAL.md` sigue pendiente del CTO; esta API no la aprueba implícitamente.

---

## 2026-09-22 — Procesador de reportes de incidentes, Fase 1: núcleo + CLI

**Estado: Fase 1 hecha y commiteada (`0203023`) — aceptación contra el dataset real PENDIENTE (el CSV no está disponible).** Rama de trabajo de todo el proyecto (Fases 1–3): `feature/incident-analyzer`.

Contexto: Roberto Díaz (Customer Support Lead) necesita analizar un mes de tickets del helpdesk legado sin enviar los datos a herramientas de IA externas (el CSV contiene emails reales). Fuente de verdad: `docs/COMPANY_INCIDENT_FILE_ANALIZER_PROJECT.md`. Plan en 4 fases: 1) núcleo + CLI, 2) API, 3) frontend en backoffice, 4) integración. Estado de las siguientes fases: ver entradas posteriores.

**Decisiones fijadas por el tech lead antes de implementar (D1–D9):** `invalid_records` cuenta filas distintas y el desglose cuenta activaciones de regla (D1); la consola muestra las 7 reglas aunque valgan 0 (D2); solo las 7 reglas del contexto invalidan — `ticket_id`/`date`/`status` fuera de formato no, y sin sección de warnings (D3); score presente no entero 1–5 → "fuera de rango", score válido en OPEN/DISCARDED permitido pero fuera del índice (D4); `strip()` + valores exactos, `agent_id` `^AGT-\d{2}$`, email = no vacío y con `@` (D5); `results.csv` en formato `metric,value` sin datos de registros (D6); tests solo con `unittest` (D7); núcleo en `packages/incident-analyzer/`, CLI fina en `scripts/analyze.py` (D8); el documento de contexto se queda en `docs/` (D9).

**Archivos añadidos:** `packages/incident-analyzer/` (`pyproject.toml`, `README.md`, `incident_analyzer/{__init__,schema,reader,validation,metrics,analyze,report,export}.py`, `tests/` con 8 módulos de test + `fixtures/incidents-synthetic.csv`); `scripts/analyze.py`.
**Archivos modificados:** `.gitignore` (Python + `data/raw/incidents/` + `results.csv`); `AGENTS.md` (§4: comando de validación del subproyecto); `memory-bank/{progress,techContext,projectbrief}.md`. Se versiona también `docs/COMPANY_INCIDENT_FILE_ANALIZER_PROJECT.md` (fuente funcional, sin PII).
**Sin cambios:** `services/` (no se creó), `uis/*`, `src/`. Ninguna dependencia añadida.

**Validación ejecutada:** `python -m unittest discover -s packages/incident-analyzer/tests -t packages/incident-analyzer` → 99 tests, 92 OK + 7 skipped (el test de aceptación `tests/test_acceptance.py`, marcado "PENDING" porque falta el dataset real). CLI ejecutada contra el fixture en modo interactivo (`y` → `results.csv`), `--export`, `--no-export` y con consola cp1252 (variante ASCII). **Los números 100/96/4 del contexto NO están verificados contra datos reales**: solo se comprobó, con un CSV simulado fuera del repo, que el test de aceptación y la aritmética del documento (media 215/56 = 3.84, porcentajes) son coherentes.

**Pendiente:**
- Obtener `incidents-nexova.csv`, colocarlo en `data/raw/incidents/` (ignorado por git) y ejecutar el test de aceptación.
- Criterios derivados de D4/D5 que API y frontend deben heredar sin reimplementar (reutilizando `incident_analyzer`): `+4`/`4.0` → score fuera de rango; `closed` en minúsculas no es `CLOSED` (fila válida, sin regla 6); un status desconocido deja el desglose por estado por debajo del total de válidos.
- ~~Fases 2–4 no iniciadas~~ — corregido: la Fase 2 se implementó el 2026-09-23 y la Fase 3 también (ver entradas de arriba); la Fase 4 sigue sin iniciar.

---

## 2026-09-20 — Propuesta de arquitectura del backend (`docs/ARCHITECTURE_PROPOSAL.md`)

**Estado: hecho (documento redactado y revisado) — pendiente de aprobación del CTO (Sergio Molina).**

Contexto: el CTO pidió una propuesta razonada de arquitectura para el primer backend propio de Nexova **antes** de implementarlo. Entregable exclusivamente documental.

**Archivos añadidos:** `docs/ARCHITECTURE_PROPOSAL.md` (patrón arquitectónico, dominios, estructura de carpetas, capas, routers, versionado, frontend/backend, CORS, persistencia, configuración, testing, riesgos, decisiones propuestas vs pendientes; referencias a documentación oficial de FastAPI, Next.js y MDN).
**Archivos modificados:** `memory-bank/progress.md` (esta entrada) y `memory-bank/techContext.md` (una nota de referencia bajo la decisión "`/services` no se crea", que sigue vigente).
**Sin cambios:** ningún archivo de implementación; `services/api/` **no** se creó; ninguna dependencia añadida; FastAPI **no** instalado; `uis/*` y `src/` intactos. **Sin impacto técnico.**

**Qué contiene la propuesta (resumen, no decisiones aprobadas):** un único servicio FastAPI en `services/api/` como monolito modular por dominios con capas internas (router → service → domain → repository); módulos MVP `candidates`, `vacancies`, `pipeline` (con notas) y `matching` como capacidad interna; versionado `/api/v1`; CORS con orígenes explícitos por entorno; PostgreSQL como motor recomendado; los 97 tests de `src/` como especificación del módulo `matching`. Todo lo anterior es **[PROPUESTA]** hasta que el CTO lo apruebe; las decisiones abiertas (autenticación, ORM, hosting, vocabulario de etapas del pipeline, exposición HTTP de `matching`, revisión de privacidad, integración del website estático) están listadas en la §19 del documento y **no** deben tratarse como resueltas.

**Validación ejecutada:** `docs/` no tiene comando de validación en la tabla de `AGENTS.md` §4 (cambio solo documental). Se verificó manualmente: (a) que todas las rutas del repositorio citadas en el documento y en `memory-bank/` existen; (b) `git status --short` / `git diff --stat` muestran únicamente los archivos listados arriba; (c) fidelidad al contexto: todos los datos de Nexova citados proceden de `contexts/CONTEXT.md` / `memory-bank/projectbrief.md`.

**Siguiente paso si se aprueba:** redactar el contrato de los dominios propuestos (`candidates` y `vacancies` primero) antes de implementarlos, añadiendo su comando de validación a la tabla de `AGENTS.md` §4 en el mismo cambio. *(Corrección 2026-09-23: esta entrada decía "redactar `services/api/SPECS.md`"; ese archivo ya existe y pertenece a la API del procesador de incidentes de Nexova. Si la propuesta se aprueba, habrá que decidir si sus dominios se añaden a ese mismo servicio y documento o van a uno nuevo.)* Ver "Próximos pasos conocidos" abajo.

---

## 2026-09-14 — Monorepo AI Setup: memory-bank, AGENTS.md, .agents/, uis/backoffice

**Estado: hecho.**

Contexto: el tech lead detectó que el repo no tenía contexto persistente para agentes. Se añadió banco de memoria (`memory-bank/`), flujo de entrega obligatorio (`AGENTS.md`), reglas y skill (`.agents/`), y un scaffold real (no solo placeholder) para `uis/backoffice`.

**Archivos añadidos:** `memory-bank/{projectbrief,techContext,progress}.md`; `AGENTS.md` (raíz); `.agents/rules/{monorepo-structure,nexova-context,app-specific-overrides}.md`; `.agents/skills/memory-bank-sync/SKILL.md`; `uis/backoffice/` completo (Next.js 16 + React 19 + TS, `lib/company.ts` con datos reales de Nexova, `app/layout.tsx`, `app/page.tsx`, `app/globals.css`, config estándar, `README.md`, `CLAUDE.md`).
**Archivos modificados:** `uis/README.md` y `uis/README.es.md` (catálogo de apps existentes, incluyendo `backoffice`).
**Sin cambios:** `uis/website/` (cero diff, confirmado); `/services` (no se creó, decisión documentada en `techContext.md`); ninguna rama existente tocada.

**Validación ejecutada:** `npm install`, `npx tsc --noEmit` (limpio), `npm run lint` (limpio), `npm run build` (compila y genera `/` estático) y `npm run dev` + verificación visual en el navegador — la ficha de `NEXOVA_COMPANY` (fundación 2011, CEO Laura Mendoza, sede Valencia + oficina Miami, 120 empleados, ~8.000.000 US$, tres líneas de negocio) se renderiza correctamente, todas dentro de `uis/backoffice/`.

**Hallazgo relevante durante la implementación:** `contexts/` está en `.gitignore` (raíz, línea 8) — nunca ha estado en git (`git ls-files contexts/` vacío). No viaja con el repositorio; solo existe en checkouts locales que ya la tenían. Se ajustó toda la documentación nueva para que `memory-bank/projectbrief.md` sea la referencia de negocio válida para quien clone el repo sin esa carpeta, y para que `contexts/CONTEXT.md` se cite como fuente ampliada "si está disponible localmente", nunca como algo garantizado.

**Desviación respecto a la rama planeada inicialmente:** el plan original (antes de corrección) proponía ramificar desde `feature/talent-pipeline-tracker` y abrir el PR contra esa misma rama, asumiendo que `main` no tenía Hitos 2/3. La inspección real mostró que el `main` **local** estaba desactualizado: `origin/main` ya tenía Hitos 2 y 3 mergeados (PRs #1, #2, #3). Corregido a petición del tech lead: rama `feature/agent-memory-bank` creada desde `origin/main`, PR con base `main` — sin tocar ninguna rama existente.

---

## Hito 3 — Talent Pipeline Tracker (`uis/talent-pipeline-tracker/`)

**Estado: hecho, mergeado a `main`** (PR #2 `Inicializar proyecto...`, PR #3 `feat: completar Talent Pipeline Tracker`).

Panel interno de gestión de candidaturas para Operaciones de Selección (Javier Almeida) / encargo urgente de Elena Vargas (L&D), con copia a Sergio Molina (CTO). Next.js 16 + React 19 + TS estricto, consume directo la API mock externa (`playground.4geeks.com/tracker/api/v1`, CORS verificado, sin proxy). Cinco incógnitas de contrato (`SPECS.md` §0, V-1 a V-5) resueltas empíricamente antes de implementar. Fuera de alcance deliberado: eliminar candidaturas (endpoint existe en la API pero no se expone en la UI).

## Hito 2 — Modelos de dominio y scoring (`src/`)

**Estado: hecho, mergeado a `main`** (PR #1 `feature/domain-models`).

Utilidades TypeScript para el motor de scoring de candidatos y matching de vacantes de Javier Almeida (Operaciones de Selección): `Candidate`, `Vacancy`, `SelectionProcess`, funciones de filtrado/búsqueda/scoring/validación. 97 tests con el runner nativo de Node (`node:test`), sin dependencias de terceros. `npm run check` = typecheck + tests.

## Hito 1 — Sitio web público (`uis/website/`)

**Estado: hecho, desplegado en Netlify.**

Landing corporativa + formulario de registro de talento para Carmen Ruiz (Marketing y Comunicación). HTML estático + Tailwind CSS v4 (Play CDN), Schema.org `Organization` JSON-LD, accesible (skip link, foco visible).

## Hito 0 — Elección de empresa

**Estado: hecho.**

Empresa elegida: **Nexova**. Justificación en `contexts/COMPANY-CHOICE.md` (local, no versionado — ver nota sobre `contexts/` en `techContext.md`); resumen de por qué en `memory-bank/projectbrief.md`.

---

## Decisiones y problemas conocidos

- ~~**`README.md` raíz desactualizado**~~ — resuelto el 2026-09-27: el `README.md` raíz ahora es el briefing de Nexova (ver entrada de arriba).
- **`main` local puede desactualizarse silenciosamente:** al iniciar este cambio, el `main` local estaba 7 commits detrás de `origin/main` (incluía Hitos 2 y 3, ya mergeados vía PR). Cualquier agente debe `git fetch` antes de asumir en qué estado está `main`.
- **`/services` ya no está vacío (2026-09-23):** contiene `services/api/`, la API del procesador de incidentes, creada por decisión del tech lead con contrato propio (`services/api/SPECS.md`). La decisión "`/services` no se crea" está marcada como superada en `techContext.md`. `docs/ARCHITECTURE_PROPOSAL.md` (backend general de Nexova: candidatos, vacantes, pipeline…) **sigue pendiente de aprobación del CTO**; `services/api/` no la adopta (p. ej. no usa `/api/v1`).
- **AUTH-03, auditoría de seguridad (2026-10-06):**
  - **H-1 corregido:** un usuario que no es admin ya no cambia `password` con `PUT /users/{id}`; solo puede hacerlo con `POST /auth/change-password`.
  - **Riesgo residual aceptado (SPECS §27):** un admin sigue pudiendo fijar contraseñas con `PUT /users/{id}`, también la suya, sin la contraseña actual. Ese cambio no invalida enlaces de reset pendientes ni se audita.
  - **No bloqueantes y sin corregir:**
    - M-1: no se cierran las sesiones al cambiar o restablecer la contraseña;
    - M-2: diferencia de tiempo en `forgot-password` según exista el email;
    - M-3: escrituras sin rate limiting en `auth.json`;
    - L-1: bcrypt antes de validar el token;
    - L-2: `PASSWORD_RESET_URL` admite `http://`;
    - L-3: el token aparece en la URL de la primera carga;
    - ~~L-4: `http.client.HTTPException` no se captura en el sender~~ — corregido el 2026-10-10 (A1 de la auditoría de gestión de errores, rama `feature/error-handling-audit`);
    - L-5: retención de las IP de la auditoría;
    - L-6: aviso de éxito oculto si hay otra sesión abierta.
- **Deuda pendiente — `LastResultStore` global al proceso, no por usuario (registrada el 2026-10-05, sin corregir):** `services/api` guarda en memoria un único "último análisis" de incidentes para todo el proceso (`services/api/SPECS.md` §6, D-API-5). Desde AUTH-01/AUTH-02 hay varios usuarios autenticados, así que un usuario puede exportar el último resultado generado por otro. Hoy el resultado solo contiene métricas agregadas (sin filas ni emails) y el frontend descarta una exportación cuyo `X-Analysis-Id` no coincide con el análisis que muestra, pero la API no lo impide. **No se corrige ahora:** es una decisión de arquitectura pendiente del tech lead, a revisar antes de llevar el módulo de incidentes a un uso multiusuario real o a la Fase 4.

- **Almacenamiento TinyDB no disponible o corrupto → 503 `storage_unavailable` (2026-10-10, A2):** antes era un 500 genérico. El caso más grave: un `auth.json` corrupto tumbaba el login y todas las rutas protegidas. Sigue sin haber escritura atómica: TinyDB reescribe el archivo entero y un corte a mitad lo deja corrupto. Ahora eso da 503 y un registro claro, pero recuperarse exige restaurar una copia o borrar el archivo (README de `services/api`). El seed del gestor, `uv run seed` y `create-admin` lo tratan desde el 2026-10-10 (S1–S3): mensaje en stderr y código de salida, sin traceback.
- **Errores capturados por los límites de error de Next (2026-10-10, por diseño):** React registra en la consola del navegador, con su mensaje y su traza, los errores que capturan `app/error.tsx` y `app/global-error.tsx` (backoffice y tracker). El código propio no los registra ni los muestra. Por eso ningún error lanzado en el código de producción puede llevar datos de la API o del usuario en su mensaje.
- **Riesgo de duplicación en `IncidentRepository.seed` (detectado el 2026-10-10, sin corregir):**
  - **Causa:** `services/api/app/modules/incident_manager/repository.py` (`seed`) hace dos escrituras no atómicas en `incidents.json`: primero `incidents_table.insert_multiple` y después `keys_table.insert_multiple` (`seed_keys`).
  - **Consecuencia:** si la segunda falla (disco lleno, permisos, el proceso muere a mitad), quedan incidencias sin su clave de origen. La siguiente ejecución del seed las vuelve a insertar, rompiendo la idempotencia. Si el fallo es de E/S, desde A2 el seed lo comunica (código 2), pero no deshace la primera escritura.
  - **Alcance:** es un problema de consistencia de datos, no de gestión de errores, así que quedó fuera de la auditoría.
  - **Arreglo posible, sin decidir:** una única escritura con las dos tablas, o reconciliar las incidencias huérfanas antes de insertar.
- **Gestor centralizado de incidencias — límites conocidos (2026-10-07, sin corregir):**
  - aceptación solo con el fixture sintético (el CSV real no está en el repo);
  - con un filtro activo, una incidencia que cambia de estado sigue en el listado hasta la siguiente carga;
  - el `seed` y la API no deben escribir a la vez en `incidents.json` (mismo criterio que D-SUP-10).
  - `/suppliers` e `/incidents` tienen el mismo patrón que causó el scroll horizontal en móvil de `/incident-manager` (elementos `sr-only` dentro de un `overflow-x-auto` sin `relative`): sin medir ni corregir; figuran como excepciones pendientes en `tests/production-source.test.mjs`.
  - Detalle en `docs/centralized-incident-manager-review.md`.

## Próximos pasos conocidos (no implementados aquí)

- **Auditoría de gestión de errores (2026-10-09):**
  - Hecha y comiteada en `feature/error-handling-audit`: `24f0e0d`, `a6f3722`, `2454dcd`, `dc91918`, `899ce1e` y el cierre del memory-bank (entradas del 2026-10-10).
  - ~~Pendiente: push y PR, que hace el usuario.~~ Integrada en `main` con la PR #18 (merge `843ae26`).
  - No se hace, con su motivo en la entrada de cierre:
    - B5: no hay contacto de soporte definido;
    - T5: se acerca más a un refactor;
    - el `BrokenPipeError` de `analyze.py`: sin test fiable en Windows;
    - el riesgo de duplicación del seed: es consistencia de datos.
- **Inventario (Hito 5):**
  - API integrada en `main` con la PR #21 (merge `8e5448e`, 2026-10-19); guía en `docs/inventory-review.md`.
  - Frontend (`uis/backoffice` → `/inventory/*`) integrado en `main` con la PR #22 (merge `410da71`, 2026-10-21); guía en `docs/inventory-frontend-review.md`. La demo de Supabase está en el neto del seed (restaurada el 2026-10-21).
  - Pendientes: la revisión por el tech lead o la CTO de D1–D11 y de las decisiones de F2–F4 de la API (`services/api/SPECS.md` §35) y de D1–D10 y sus ajustes del frontend (`docs/inventory-frontend-review.md`, «Decisiones y ajustes»); y lo que recogen las secciones «Lo que no está verificado» de `docs/inventory-review.md` y de `docs/inventory-frontend-review.md`.
- **Gestor centralizado de incidencias:** hecho en F1–F6 en `feature/centralized-incident-manager` (commits `164a183`, `959a65b`, `ef040f5`, `d7ce215`, `7ce4101`, `ca0bf00` y el arreglo móvil `ee944ae`). Integrado en `main` con la PR #17 (merge `6dfa013`, 2026-10-08). Guía de revisión: `docs/centralized-incident-manager-review.md`. Pendientes: la revisión de P4-1…P4-13 (decisiones del usuario) por el tech lead o la CTO, la aceptación con el CSV real y la verificación visual en móvil y con lector de pantalla.
- **Backend general de Nexova:** `docs/ARCHITECTURE_PROPOSAL.md` está pendiente de revisión por el CTO. Si se aprueba, sus dominios (candidatos, vacantes, pipeline, matching) tendrán que decidir cómo convivir con el `services/api/` ya existente del procesador de incidentes (mismo servicio o no, prefijo `/api/v1` o no). Nada de eso se ha iniciado.
- **Procesador de incidentes:** Fases 1, 2 y 3 (`/incidents` en `uis/backoffice`) hechas e integradas en `main` (PR #6). Existe un fixture sintético de aceptación que reproduce las cifras del contexto (entrada 2026-09-27, PR #7). Pendientes: el test de aceptación con el CSV real (las cifras 100/96/4 no están verificadas con datos reales) y la Fase 4 (integración). Antes de la Fase 4 o de un uso multiusuario real, revisar la deuda de `LastResultStore` (ver "Decisiones y problemas conocidos").
- `uis/backoffice` es un punto de entrada — tiene, según «Alcance actual» de `uis/backoffice/CLAUDE.md`, la vista de entrada (`/`), `/incidents`, `/suppliers`, `/incident-manager` (PR #17) e `/inventory/*` (PR #22), todas protegidas por la autenticación (AUTH-02, con las vistas de contraseña de AUTH-03); el resto de capacidades (portal de RRHH, ventas, dirección ejecutiva) requieren su propio contexto de hito antes de implementarse.
- **Directorio de proveedores:** hecho e integrado en `main` con el PR #9 (entrada 2026-09-29). Migración futura de TinyDB a Postgres cuando exista el ORM (decisión del tech lead) — `User`/`Profile` de AUTH-01 **no** migran: se quedan en TinyDB y Postgres solo guardará `user_uuid`.
- **AUTH-01:** hecho e integrado en `main` con el PR #10 (entrada 2026-09-30). Su siguiente fase (que el frontend envíe el token y `PUT` en CORS) la cubrió AUTH-02.
- **AUTH-03:** implementado en `feature/password-reset` (entradas 2026-10-05 y 2026-10-06), validado de extremo a extremo con email real y con H-1 de la auditoría corregido. Commits `cb9d0d5` y `2a1926a`, integrados en `main` con la PR #16 (merge `677e735`, 2026-10-07). La guía para revisarlo está en `docs/auth-password-reset.md`. El merge no aprueba las propuestas P3-1…P3-6 ni decide sobre M-1, M-2 y M-3, que siguen pendientes.
- **AUTH-02:** hecho e integrado en `main` con la PR #13 (merge `a4b6369`, entrada 2026-10-02 / 2026-10-05). Pendientes: revisión de las propuestas P-1…P-7 (`docs/auth-frontend.md` §3.3), registro desde la UI del tracker y refresh tokens (fuera de alcance). Los 4 errores de lint `react-hooks/set-state-in-effect` del tracker son anteriores a AUTH-02.

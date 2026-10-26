# Lighthouse — medición inicial (F1)

Medición de partida de la auditoría de rendimiento (brief en [`docs/perf-audit-brief.md`](../../docs/perf-audit-brief.md)). Esta fase solo mide: aquí no se corrige nada ni se interpretan causas raíz (eso es F3, en `AUDIT.md`).

**Fuente de las cifras.** Todas salen del JSON guardado en cada caso. Las únicas excepciones son las ejecuciones que no se guardaron (§4), que las anotó el usuario a mano. Las capturas (`.png`) son la evidencia visual.

## 1. Condiciones

| | |
|---|---|
| Fecha | 2026-10-26 (21:52) a 2026-10-27 (00:13), hora local (Romance Standard Time, UTC+1). Los `fetchTime` del JSON están en UTC |
| Commit medido | `fb3cb15` (rama `feature/perf-audit`). Su código es el de `6877599` (merge de la PR #24); `fb3cb15` solo añade el brief |
| Herramienta | Panel Lighthouse de Chrome DevTools, ejecutado por el usuario. No se usó el CLI de Lighthouse |
| Lighthouse | 13.4.1 en los 12 JSON (`lighthouseVersion`) |
| Chrome | `Chrome/155.0.0.0` en los 12 JSON (`environment.hostUserAgent`). El user agent reducido de Chrome no da la versión menor |
| Navegador | Ventana de incógnito, sin extensiones, una pestaña |
| Modo | Navigation (`gatherMode: navigation`), throttling simulado (`throttlingMethod: simulate`), las 4 categorías |
| Mobile | `formFactor: mobile`; viewport de 412 px (DevTools emula el dispositivo). Throttling: RTT 150 ms, 1638,4 kbps, CPU ×4 |
| Desktop | `formFactor: desktop`; viewport de 1526 px de ancho, el de la ventana del usuario (ancho de `fullPageScreenshot`). Throttling: RTT 40 ms, 10 240 kbps, CPU ×1 |
| `benchmarkIndex` | Entre 3569,5 y 3892,5 según el caso (columna en §2) |
| Datos del backoffice | La API de Docker (`api`, `healthy`), con TinyDB de desarrollo (97 incidencias, 15 proveedores) y el inventario en la demo de Supabase. Solo lectura: ningún alta ni cambio de estado durante la medición |

### Servidores

- **Sitio** (`uis/website`): `node uis/serve-website.mjs` en `http://localhost:3000`, en el host. Es el mismo servidor estático del contenedor `ui`, que se paró durante la medición. Envía `Cache-Control: no-store`, sin compresión y por HTTP/1.1, mientras que en producción el sitio lo publica Netlify. Tailwind llega por el Play CDN: `@tailwindcss/browser@4` resuelve a la **4.3.3** (jsDelivr).
- **Backoffice** (`uis/backoffice`): build de producción (`npm run build`) y `npm run start -- -p 3003`. Next.js 16.3.2. Las variables solo se definieron en la sesión de PowerShell: `API_INTERNAL_URL=http://localhost:8000`, `NEXT_PUBLIC_API_URL=/backend` y `NEXT_PUBLIC_INVENTORY_API_URL=/backend`. El navegador solo habló con `localhost:3003/backend/…`.

### «Clear storage» y sesión

| Casos | «Clear storage» | Sesión | `disableStorageReset` en el JSON |
|---|---|---|---|
| Sitio (1–4) | marcado | — | `false` |
| Login en frío (9, 10) | marcado | sin sesión | `false` |
| Vistas del backoffice (5–8, 11, 12) | desmarcado | con sesión (usuario `diegoreynoso746@gmail.com`; se volvió a iniciar sesión antes del caso 8 por la caducidad de 30 min del token) | `true` |

En el backoffice se descartó una ejecución de calentamiento por caso. En el login no hubo calentamiento.

### URLs

- Sitio: `http://localhost:3000/` y `http://localhost:3000/application.html`.
- Backoffice: `http://localhost:3003/login`, `/incident-manager`, `/suppliers` y `/inventory/products`.

## 2. Comprobaciones de cada JSON

| Caso | Archivo | `finalDisplayedUrl` | `formFactor` | LH | `fetchTime` (UTC → local) | `benchmarkIndex` |
|---|---|---|---|---|---|---|
| 1 | `website/index/index-mobile.json` | `http://localhost:3000/` | mobile | 13.4.1 | 20:52:47Z → 21:52:47 | 3892,5 |
| 2 | `website/index/index-desktop.json` | `http://localhost:3000/` | desktop | 13.4.1 | 21:05:10Z → 22:05:10 | 3728,5 |
| 3 | `website/application/application-mobile.json` | `…/application.html` | mobile | 13.4.1 | 21:17:49Z → 22:17:49 | 3862,5 |
| 4 | `website/application/application-desktop.json` | `…/application.html` | desktop | 13.4.1 | 21:21:58Z → 22:21:58 | 3724,5 |
| 9 | `backoffice/login/login-mobile.json` | `http://localhost:3003/login` (es el caso) | mobile | 13.4.1 | 21:56:19Z → 22:56:19 | 3825,5 |
| 10 | `backoffice/login/login-desktop.json` | `http://localhost:3003/login` (es el caso) | desktop | 13.4.1 | 22:00:07Z → 23:00:07 | 3730,5 |
| 5 | `backoffice/incident-manager/incident-manager-desktop.json` | `…/incident-manager` | desktop | 13.4.1 | 22:27:04Z → 23:27:04 | 3726,5 |
| 6 | `backoffice/incident-manager/incident-manager-mobile.json` | `…/incident-manager` | mobile | 13.4.1 | 22:23:56Z → 23:23:56 | 3671,5 |
| 7 | `backoffice/suppliers/suppliers-desktop.json` | `…/suppliers` | desktop | 13.4.1 | 22:52:20Z → **23:52:20** | 3569,5 |
| 11 | `backoffice/suppliers/suppliers-mobile.json` | `…/suppliers` | mobile | 13.4.1 | 22:34:57Z → 23:34:57 | 3833,5 |
| 8 | `backoffice/inventory-products/inventory-products-desktop.json` | `…/inventory/products` | desktop | 13.4.1 | 23:13:56Z → 00:13:56 (día 27) | 3643 |
| 12 | `backoffice/inventory-products/inventory-products-mobile.json` | `…/inventory/products` | mobile | 13.4.1 | 23:09:03Z → 00:09:03 (día 27) | 3653,5 |

- **Sin redirección a `/login`:** en todas las vistas con sesión, `requestedUrl`, `finalDisplayedUrl` y `mainDocumentUrl` coinciden.
- **Sin avisos:** `runWarnings` está vacío en los 12 JSON.
- **Hora de las ejecuciones:** el `fetchTime` de cada JSON coincide con la hora que anotó el usuario para la ejecución guardada, salvo en el caso 7:
  - las notas lo daban como la ejecución 2, a las 23:51:14;
  - el JSON es de las **23:52:20**, una ejecución posterior;
  - las tres ejecuciones de ese caso dieron las mismas cifras, así que la tabla no cambia.
- **Variación entre ejecuciones:** la Performance no varía más de 1 punto en ningún caso (§4), muy por debajo del umbral de aviso de 10 puntos.
- **Captura renombrada:** `incident-manager-desktop.png.png` pasó a `incident-manager-desktop.png`, como las demás.

## 3. Resultados (ejecución guardada en cada JSON)

FCP, LCP, TBT, CLS y SI son los valores simulados de Lighthouse. TTFB es la auditoría `server-response-time` (respuesta del documento raíz, observada). El elemento LCP sale de `lcp-breakdown-insight`.

| Caso | App | Página | Modo | Condición | Perf | A11y | BP | SEO | FCP | LCP | TBT | CLS | SI | TTFB | Elemento LCP |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | website | index | mobile | sin sesión, storage limpio | 98 | 100 | 100 | 100 | 1,9 s | 2,1 s | 10 ms | 0 | 1,9 s | 2 ms | `section#inicio … p.mt-6` (párrafo del hero) |
| 2 | website | index | desktop | sin sesión, storage limpio | 100 | 100 | 100 | 100 | 0,5 s | 0,5 s | 0 ms | 0 | 0,5 s | 2 ms | `a.inline-block > img.h-10` (`src/img/logo.svg`, el logo del header) |
| 3 | website | application | mobile | sin sesión, storage limpio | 98 | 100 | 100 | 100 | 1,9 s | 2,0 s | 30 ms | 0 | 1,9 s | 2 ms | `p#form-instructions` |
| 4 | website | application | desktop | sin sesión, storage limpio | 100 | 100 | 100 | 100 | 0,5 s | 0,5 s | 0 ms | 0 | 0,5 s | 1 ms | `p#form-instructions` |
| 9 | backoffice | login | mobile | **en frío** (sin sesión, storage limpio) | 100 | 100 | 100 | 100 | 0,8 s | 1,7 s | 20 ms | 0 | 0,8 s | 2 ms | `section.mx-auto > div.flex > p.text-sm` («Entra con tu email…») |
| 10 | backoffice | login | desktop | **en frío** (sin sesión, storage limpio) | 100 | 100 | 100 | 100 | 0,2 s | 0,4 s | 0 ms | 0,003 | 0,2 s | 2 ms | `section.mx-auto > div.flex > p.text-sm` («Entra con tu email…») |
| 5 | backoffice | incident-manager | desktop | con sesión | 100 | 100 | 100 | 100 | 0,2 s | 0,3 s | 0 ms | 0,032 | 0,2 s | 1 ms | `main.mx-auto > div.flex > p.text-sm` (descripción de la página) |
| 6 | backoffice | incident-manager | mobile | con sesión | **82** | 100 | 100 | 100 | 0,6 s | 1,0 s | 20 ms | **0,373** | 0,6 s | 2 ms | `main.mx-auto > div.flex > p.text-sm` (descripción de la página) |
| 7 | backoffice | suppliers | desktop | con sesión | 100 | 100 | 100 | 100 | 0,2 s | 0,2 s | 0 ms | 0,032 | 0,2 s | 1 ms | no informado (el JSON solo trae TTFB y *render delay*, sin nodo) |
| 11 | backoffice | suppliers | mobile | con sesión | 95 | 100 | 100 | 100 | 0,6 s | 1,1 s | 80 ms | **0,136** | 0,6 s | 2 ms | `main.mx-auto > div.flex > p.text-sm` (descripción de la página) |
| 8 | backoffice | inventory/products | desktop | con sesión | 100 | 100 | 100 | 100 | 0,2 s | 0,2 s | 0 ms | 0,032 | 0,2 s | 3 ms | no informado (el JSON solo trae TTFB y *render delay*, sin nodo) |
| 12 | backoffice | inventory/products | mobile | con sesión | 95 | 100 | 100 | 100 | 0,6 s | 0,9 s | 60 ms | **0,135** | 0,6 s | 2 ms | `main.mx-auto > div.flex > div.flex > p.text-sm` (descripción de la página) |

Los casos 9–12 se añadieron a los 8 previstos: el login en frío (mobile y desktop) y suppliers e inventory/products también en mobile. Así las tres vistas con datos quedan medidas en los dos modos.

**Capturas.** Las capturas coinciden con su JSON en todos los casos, con dos excepciones:

- **Caso 1 (index mobile):** la captura es otra ejecución, de las 22:09:55. Tiene las mismas puntuaciones y FCP; el LCP es 1,9 s, frente a 2,1 s en el JSON. La cifra de referencia es la del JSON.
- **Caso 2 (index desktop):** la captura es la ejecución 3 (22:06:02), con cifras idénticas a las del JSON (ejecución 1).

### Criterio de «corrección requerida» (decidido por el usuario)

Una corrección es **requerida** en dos supuestos:

- una métrica medida incumple su umbral:
  - Performance < 90;
  - LCP > 2,5 s;
  - CLS > 0,1;
  - TBT > 200 ms, como aproximación de laboratorio al INP (en modo Navigation, Lighthouse no mide INP);
- es una auditoría fallida con ahorro estimado que la skill (core-web-vitals / performance, que se instalan en F2) señala como causa.

Todo lo demás es sugerencia.

**Métricas que incumplen el umbral en esta medición** (la parte de la skill se evalúa en F2–F3):

| Caso | Métrica fuera de umbral |
|---|---|
| 6 — incident-manager mobile | Performance 82 (< 90) y CLS 0,373 (> 0,1) |
| 11 — suppliers mobile | CLS 0,136 (> 0,1) |
| 12 — inventory/products mobile | CLS 0,135 (> 0,1) |

En el sitio corporativo ninguna métrica incumple el umbral: el LCP mobile más alto es 2,1 s, por debajo de 2,5 s.

## 4. Todas las ejecuciones (según las notas del usuario)

Las cifras de las ejecuciones no guardadas las anotó el usuario. La ejecución guardada coincide con su JSON. Hora local.

### Sitio corporativo — 2026-10-26

- **Caso 1 (index mobile).** La guardada es la run 1:
  - run 1 (21:52:47, JSON): Perf 98, FCP 1,9 s, LCP 2,1 s, TBT 10 ms, CLS 0, SI 1,9 s;
  - run 2: Perf 98, FCP 1,9 s, LCP 2,0 s, TBT 10 ms, CLS 0, SI 1,9 s;
  - run 3: Perf 98, FCP 1,9 s, LCP 2,0 s, TBT 10 ms, CLS 0, SI 1,9 s;
  - captura: una ejecución posterior (22:09:55), con Perf 98, FCP 1,9 s, LCP 1,9 s, TBT 10 ms, CLS 0, SI 1,9 s.
- **Caso 2 (index desktop).** La guardada es la run 1; la captura es la run 3. Las tres dieron Perf 100, FCP 0,5 s, LCP 0,5 s, TBT 0 ms, CLS 0, SI 0,5 s:
  - run 1: 22:05:10 (JSON);
  - run 2: 22:05:41;
  - run 3: 22:06:02 (captura).
- **Caso 3 (application mobile).** La guardada es la run 3, la mediana:
  - run 1 (22:16:03): Perf 98, FCP 1,9 s, LCP 2,0 s, TBT 30 ms, CLS 0, SI 1,9 s;
  - run 2 (22:16:55): Perf 98, FCP 1,9 s, LCP 2,0 s, TBT 20 ms, CLS 0, SI 1,9 s;
  - run 3 (22:17:49, JSON): Perf 98, FCP 1,9 s, LCP 2,0 s, TBT 30 ms, CLS 0, SI 1,9 s.
- **Caso 4 (application desktop).** La guardada es la run 3, la mediana. Las tres dieron Perf 100, FCP 0,5 s, LCP 0,5 s, TBT 0 ms, CLS 0, SI 0,5 s:
  - run 1: 22:20:58;
  - run 2: 22:21:39;
  - run 3: 22:21:58 (JSON).

### Backoffice — 2026-10-26/27

- **Caso 9 (login mobile, en frío; añadido).** La guardada (captura y JSON) es una cuarta ejecución. La mediana de las 3 primeras daba Perf 99; la guardada da 100:
  - run 1 (22:31:16): Perf 99, FCP 0,8 s, LCP 2,2 s, TBT 50 ms, CLS 0, SI 0,8 s;
  - run 2 (22:31:57): Perf 99, FCP 0,8 s, LCP 2,1 s, TBT 20 ms, CLS 0, SI 0,8 s;
  - run 3 (22:32:33): Perf 100, FCP 0,8 s, LCP 1,7 s, TBT 60 ms, CLS 0, SI 0,8 s;
  - run 4 (22:56:19, guardada): Perf 100, FCP 0,8 s, LCP 1,7 s, TBT 20 ms, CLS 0, SI 0,8 s.
- **Caso 10 (login desktop, en frío; añadido).** La guardada es la run 3, la mediana. Las tres dieron Perf 100, FCP 0,2 s, LCP 0,4 s, TBT 0 ms, CLS 0,003, SI 0,2 s:
  - run 1: 22:58:11;
  - run 2: 22:59:44;
  - run 3: 23:00:07 (JSON).
- **Caso 5 (incident-manager desktop).** La guardada es la run 3, la mediana:
  - run 1 (23:26:05): Perf 100, FCP 0,2 s, LCP 0,3 s, TBT 10 ms, CLS 0,032, SI 0,4 s;
  - run 2 (23:26:38): Perf 100, FCP 0,2 s, LCP 0,3 s, TBT 0 ms, CLS 0,032, SI 0,2 s;
  - run 3 (23:27:04, JSON): Perf 100, FCP 0,2 s, LCP 0,3 s, TBT 0 ms, CLS 0,032, SI 0,2 s.
- **Caso 6 (incident-manager mobile).** La guardada (captura y JSON) es una cuarta ejecución:
  - runs 1, 2 y 3 (23:21:07, 23:21:40 y 23:22:00): Perf 82, FCP 0,6 s, LCP 0,9 s, CLS 0,373, SI 0,6 s, con TBT 60, 50 y 50 ms;
  - run 4 (23:23:56, guardada): Perf 82, FCP 0,6 s, LCP 1,0 s, TBT 20 ms, CLS 0,373, SI 0,6 s.
- **Caso 7 (suppliers desktop).** Las tres ejecuciones dieron Perf 100, FCP 0,2 s, LCP 0,2 s, TBT 0 ms, CLS 0,032, SI 0,2 s. Según las notas, la guardada era la run 2, a las 23:51:14, pero **el JSON es de las 23:52:20** (§2).
- **Caso 11 (suppliers mobile; añadido).** La guardada (captura y JSON) es la run 3:
  - run 1 (23:33:02): Perf 95, FCP 0,6 s, LCP 1,0 s, TBT 50 ms, CLS 0,136, SI 0,6 s;
  - run 2 (23:33:51): Perf 95, FCP 0,6 s, LCP 1,1 s, TBT 60 ms, CLS 0,136, SI 0,6 s;
  - run 3 (23:34:57, guardada): Perf 95, FCP 0,6 s, LCP 1,1 s, TBT 80 ms, CLS 0,136, SI 0,6 s.
- **Caso 12 (inventory/products mobile; añadido).** La guardada (captura y JSON) es una cuarta ejecución:
  - runs 1, 2 y 3 (00:04:41, 00:05:05 y 00:05:36): Perf 95, FCP 0,6 s, LCP 0,9 s, TBT 50 ms, CLS 0,135, SI 0,6 s;
  - run 4 (00:09:03, guardada): Perf 95, FCP 0,6 s, LCP 0,9 s, TBT 60 ms, CLS 0,135, SI 0,6 s.
- **Caso 8 (inventory/products desktop).** La guardada es la run 3, la mediana. Las tres dieron Perf 100, FCP 0,2 s, LCP 0,2 s, TBT 0 ms, CLS 0,032, SI 0,2 s:
  - run 1: 00:11:44;
  - run 2: 00:13:34;
  - run 3: 00:13:56 (JSON).

## 5. Observado, sin causa raíz todavía

Esta sección es material para F3: se anota lo que dicen los JSON, sin concluir nada.

### 5.1 Auditorías fallidas y ahorro estimado

**Sitio corporativo** (los cuatro casos salvo donde se indica):

| Auditoría | Qué señala | Ahorro estimado | Casos |
|---|---|---|---|
| `render-blocking-insight` | `https://cdn.jsdelivr.net/npm/@tailwindcss/browser@4` (≈57 KB) | FCP/LCP 1150 ms (index mobile), 1100 ms (application mobile), 300 ms (los dos desktop; en index desktop, FCP 300 y LCP 0) | 1–4 |
| `unused-javascript` | El mismo script del CDN (`@tailwindcss/browser@4.3.3/dist/index.global.js`), 21 KiB sin usar de 56 KiB | FCP 150 ms (index mobile); FCP/LCP 50 ms (index desktop) | 1, 2 |
| `image-delivery-insight` | `src/img/ambiente-trabajo-nexova.jpg`: 1920×1156 (308 KB) mostrada a 576×347 (desktop) o 380×229 (mobile) | 274 KiB (desktop) y 295 KiB (mobile); sin ahorro en métricas | 1, 2 |
| `unsized-images` | `src/img/logo.svg` (`<img class="h-10 w-auto">`, sin `width`/`height`) | sin ahorro de CLS (CLS 0) | 1–4 |
| `lcp-discovery-insight` | El LCP es `logo.svg` y falta `fetchpriority=high` (sí es descubrible y no es *lazy*) | sin ahorro estimado | 2 |
| `unminified-javascript` | `src/js/validations.js` (12 KB, 4 KiB recuperables) | sin ahorro en métricas | 3, 4 |
| `network-dependency-tree-insight` | Cadena documento → script del CDN; ningún origen con `preconnect` | informativa | 1–4 |
| `cache-insight` | Solo el script del CDN (TTL de 7 días, 6 KiB). Los archivos locales no aparecen, porque el servidor local los envía con `no-store` | 6 KiB; sin ahorro en métricas | 1–4 |
| `document-latency-insight` | «No compression applied» en el HTML (10 KiB en index, 14 KiB en application). Redirecciones y respuesta del servidor, bien | sin ahorro en métricas | 1–4 |

**Backoffice:**

| Auditoría | Qué señala | Ahorro estimado | Casos |
|---|---|---|---|
| `legacy-javascript-insight` | `_next/static/chunks/0zutzion2550z.js` (polyfills como `Array.prototype.at` y `Array.prototype.flat`) | 13–14 KiB; FCP/LCP 0 | 5–12 |
| `unused-javascript` | El mismo chunk, 26 KiB sin usar de 72 KiB | 26 KiB; FCP/LCP 0 | 9, 10 (login en frío) |
| `render-blocking-insight` | `_next/static/chunks/3041c5xfhjw05.css` (4,8 KB) | FCP/LCP 150 ms en el login mobile en frío. Con sesión, el CSS ya está en la caché (0 bytes transferidos) y no hay ahorro | 9 (ahorro); 5–8, 10–12 (sin ahorro) |
| `cls-culprits-insight` / `layout-shifts` | Ver §5.3 | CLS 0,373 / 0,136 / 0,135 | 6, 11, 12 (fallan); 5, 7, 8, 10 (desplazamientos menores) |
| `network-dependency-tree-insight` | Cadena documento → CSS; ningún origen con `preconnect` | informativa | 5–12 |
| `bf-cache` | «The cache was intentionally cleared» (Lighthouse lo marca como *Not actionable*) | — | 5 |

**Artefactos del servidor local** (se documentan y **no se corrigen** en `serve-website.mjs`):

- **Compresión:** `document-latency-insight` → `usesCompression: false`.
- **Caché:** `Cache-Control: no-store` en los archivos locales, que quedan fuera de `cache-insight`.
- **HTTP/2:** `modern-http-insight` pasa (localhost), pero el servidor solo habla HTTP/1.1.
- **TTFB:** de 1–3 ms en todos los casos, nada representativo de producción (Netlify en el sitio, el servidor del backoffice en un despliegue real).

### 5.2 Elemento LCP de cada caso

| Caso | Elemento LCP | Desglose (`lcp-breakdown-insight`, observado) |
|---|---|---|
| 1 index mobile | `p.mt-6` del hero (`section#inicio`), texto | TTFB 6 ms, *render delay* 108 ms |
| 2 index desktop | `img.h-10` = `src/img/logo.svg`, imagen | TTFB 6 ms, *load delay* 44 ms, *load duration* 21 ms, *render delay* 88 ms |
| 3 application mobile | `p#form-instructions`, texto | TTFB 5 ms, *render delay* 124 ms |
| 4 application desktop | `p#form-instructions`, texto | TTFB 5 ms, *render delay* 148 ms |
| 9 login mobile | `p.text-sm` («Entra con tu email…»), texto | TTFB 7 ms, *render delay* 71 ms |
| 10 login desktop | `p.text-sm` («Entra con tu email…»), texto | TTFB 7 ms, *render delay* 103 ms |
| 5 incident-manager desktop | `p.text-sm`, descripción de la página | TTFB 4 ms, *render delay* 182 ms |
| 6 incident-manager mobile | `p.text-sm`, descripción de la página | TTFB 5 ms, *render delay* 166 ms |
| 7 suppliers desktop | sin nodo en el JSON | TTFB 4 ms, *render delay* 63 ms |
| 11 suppliers mobile | `p.text-sm`, descripción de la página | TTFB 5 ms, *render delay* 206 ms |
| 8 inventory/products desktop | sin nodo en el JSON | TTFB 6 ms, *render delay* 84 ms |
| 12 inventory/products mobile | `p.text-sm`, descripción de la página | TTFB 6 ms, *render delay* 170 ms |

- En el index el elemento LCP cambia según el modo: en mobile es el párrafo del hero y en desktop el logo.
- El LCP de application y de las vistas del backoffice es siempre un párrafo de texto, no una imagen ni una tabla.

### 5.3 `layout-shifts` en los casos con CLS distinto de 0

Ningún JSON trae subelementos de causa (`cause`/`extra`) en los desplazamientos.

**Desktop:** las tres vistas dan 0,032, pero **el elemento no es el mismo en las tres**.

| Caso | Elemento | Puntuación |
|---|---|---|
| 5 incident-manager | `body.flex > main.mx-auto` (`<main class="mx-auto flex w-full max-w-4xl flex-1 flex-col gap-8 px-4 py-8">`) | 0,032271 |
| 7 suppliers | `body.flex > header.border-b > div.mx-auto` (el contenedor del header: «Nexova · Backoffice», enlaces de navegación…) | 0,032270 |
| 8 inventory/products | `body.flex > header.border-b > div.mx-auto` (el mismo contenedor del header) | 0,032270 |
| 10 login (en frío) | `body.flex > main.mx-auto` | 0,003 |

**Mobile:** el mismo desplazamiento de `main` se repite en las tres vistas con **idéntica puntuación (0,1336942940441483)**. Lo que se suma encima depende de la vista:

| Caso | Desplazamientos | Total |
|---|---|---|
| 6 incident-manager | `main.mx-auto` 0,1337 + `section[aria-labelledby="incident-list-heading"]` (la sección del listado, «97 incidencias») **0,2344** + `div[role="group"][aria-label="Filtros del listado de incidencias"]` 0,0052 | 0,373 |
| 11 suppliers | `main.mx-auto` 0,1337 + `div[role="group"][aria-label="Filtros del directorio"]` 0,0026 | 0,136 |
| 12 inventory/products | `main.mx-auto` 0,1337 + `p.text-xs` («Nivel de stock: Agotado (0) · Bajo…») 0,0014 | 0,135 |
| 9 login (en frío) | ninguno | 0 |

**Otros datos para F3:**

- **Altura de página:** la de incident-manager mobile es 8504 px (97 filas); la de suppliers mobile, 3012 px, y la de inventory/products mobile, 1264 px.
- **CLS observado:** `observedCumulativeLayoutShift` coincide con el CLS informado en todos los casos.

### 5.4 Hueco entre FCP y LCP en el login (en frío)

| Caso | FCP (simulado) | LCP (simulado) | Hueco | FCP / LCP observados (sin throttling) | TTI |
|---|---|---|---|---|---|
| 9 login mobile | 757 ms | 1657 ms | **900 ms** | 78 ms / 78 ms | 2,4 s |
| 10 login desktop | 212 ms | 412 ms | 200 ms | 109 ms / 109 ms | 0,4 s |

- **El hueco solo aparece en la simulación:** en la traza observada, FCP y LCP caen en el mismo instante en los dos modos.
- **Variación entre ejecuciones:** en mobile, el LCP cambió de una a otra (2,2 / 2,1 / 1,7 / 1,7 s) con el FCP fijo en 0,8 s.
- **Mismo elemento LCP** en los dos modos: el párrafo `p.text-sm`, sin imagen.
- **Recursos en el login en frío:** 174 KiB en total, con el CSS de 4,8 KB bloqueante (150 ms de ahorro estimado en mobile) y el chunk `0zutzion2550z.js` con 26 KiB sin usar.

### 5.5 Peso total por página (`total-byte-weight`)

- **Sitio:**
  - index: 377 KiB (desktop) / 376 KiB (mobile);
  - application: 93 KiB.
- **Backoffice:**
  - login en frío: 174 KiB;
  - con sesión y caché: 22–27 KiB.

# REPORT — Mejoras de rendimiento de los dos frontends

Informe de cierre de la auditoría de rendimiento ([`docs/perf-audit-brief.md`](docs/perf-audit-brief.md)): qué se cambió, cuánto mejoró y qué tuvo más impacto.

| Documento | Qué contiene |
|---|---|
| [`AUDIT.md`](AUDIT.md) | El análisis inicial: puntuaciones, causas raíz y refactorización |
| [`audit/after/runs.md`](audit/after/runs.md) | El registro de la medición final y de las intermedias |

Rama `feature/perf-audit`.

## 1. Resumen

- **El backoffice era lo único fuera de umbral, y ya no lo está.** Las tres vistas con datos superaban el umbral de CLS (0,1) en mobile, y `/incident-manager` tenía una Performance de 82. Con dos correcciones dirigidas al layout (H1 y H2), el CLS mobile pasa a:
  - **0** en `/incident-manager` (antes 0,373);
  - **0,003** en `/suppliers` (antes 0,136);
  - **0,001** en `/inventory/products` (antes 0,135).

  La Performance de las tres vistas pasa a **99**; en `/incident-manager`, desde 82.
- **El sitio corporativo no incumplía ningún umbral, pero tenía el LCP más alto de toda la medición** (2,1 s en mobile). Al cambiar el Play CDN de Tailwind por CSS precompilado (H3), el FCP mobile baja de 1,9 a 0,9 s y el LCP de 2,1 a 1,2 s en el index. Con la foto en tamaños adaptados (H4), el index pesa 79 KiB en mobile en lugar de 376.
- **Se extrajo un componente reutilizable** (R1, `TableScroll`), que además corrige la regla del `relative` que faltaba en 4 tablas.
- **La conclusión se apoya en los 6 casos móviles,** medidos con el mismo viewport antes y después (412 px). Los 6 desktop se midieron con anchos de ventana distintos (1526 frente a 870 px) y van como complementarios (§3 y §6).

## 2. Cambios aplicados

Un problema por commit, en este orden.

### H1 — La cabecera del backoffice reserva su espacio mientras se valida la sesión · `4e23d91`

- **Causa:** `AccountNav` no pintaba nada hasta que `GET /auth/me` confirmaba la sesión, y luego pintaba 8 elementos. La cabecera crecía de 53 a 170 px en mobile y empujaba todo `main`: 0,1337 de CLS, idéntico en las tres vistas. La cuenta de la geometría está en `AUDIT.md` §3.1.
- **Qué se cambió:** en las rutas protegidas, mientras se comprueba la sesión, la cabecera pinta el hueco de la navegación:
  - invisible, `aria-hidden` e `inert`;
  - con `<span>` sin `href`, para que Next no precargue rutas protegidas;
  - la decisión es una función pura, `headerNavMode`, probada con Jest, más una regla estática;
  - sin tocar el guard ni la estrategia de sesión (D10).
- **Impacto medido** (intermedia, `audit/after/steps/H1/`): desaparece el desplazamiento de `main`.
  - `/suppliers` mobile: CLS 0,136 → 0,003 y Performance 95 → 100;
  - `/incident-manager` mobile: CLS 0,373 → 0,240 (le faltaba H2).

  Esa ejecución se hizo con 3 extensiones de Chrome activas, que inflaron el FCP de 0,6 a 0,9 s. El CLS no se ve afectado; está documentado en `audit/after/runs.md` §2.

### Arreglo del contrato del inventario con CRLF · `126d067`

- **Causa:** con `core.autocrlf=true`, la copia de trabajo de `vocabulary.py` tiene CRLF, y la regex de un test esperaba `\n`. Fallaban 3 tests sin que nada hubiera cambiado.
- **Qué se cambió:** `\r?\n` en esa regex, con una mutación de control que sigue detectando una diferencia real.
- **Impacto:** `node:test` del backoffice vuelve a estar en verde (499/499 entonces; 504/504 al cerrar).

### H2 — El resumen de `/incident-manager` reserva su espacio mientras carga · `4039279`

- **Causa:** mientras cargaba, el panel de resumen era una sola fila. Al llegar los datos pintaba 4 listas apiladas, con 19 filas, y empujaba el listado: 0,2344 de CLS.
- **Qué se cambió:** mientras carga, el panel pinta la misma rejilla con una fila por valor del vocabulario y «—» en lugar de cada número. El contrato garantiza esas filas, así que la altura es idéntica: 654 px a 375 y 412 de ancho, y 298 a 1024. El error aislado del resumen sigue funcionando.
- **Impacto medido** (intermedia, `audit/after/steps/H2/`, ventana limpia): en `/incident-manager` mobile, CLS 0,240 → **0** y Performance 88 → **100**. Desaparecen el 0,2344 del listado y también el 0,0052 de los filtros. El FCP vuelve a 0,6 s, lo que confirma que el 0,9 s de H1 era por las extensiones.

### H3 — Tailwind precompilado en lugar del Play CDN · `5823cf7`

- **Causa:** las 3 páginas del sitio cargaban `@tailwindcss/browser@4` como un `<script>` síncrono en el `<head>`. Es JavaScript de otro origen que genera el CSS en el navegador antes de pintar. `render-blocking-insight` le atribuía hasta 1150 ms de FCP/LCP en mobile.
- **Qué se cambió:**
  - el CSS se genera con el CLI de Tailwind 4.3.3, la misma versión que servía el CDN, y se enlaza como hoja local minificada de 17,5 KB, versionada porque Netlify publica sin build;
  - el CLI escanea los 3 HTML y `src/js/*.js`;
  - el comando está en el `uis/website/README.md` nuevo;
  - sin cambio visual: 0 diferencias en estilos calculados y cajas, en 11 estados (desktop y 375 px, menú y formulario).
- **Impacto medido** (final, por auditorías):
  - el script desaparece de `render-blocking-insight`; solo queda `styles.css`, con 0–50 ms estimados;
  - FCP mobile 1,9 → 0,9 s en el index y en application;
  - LCP mobile 2,1 → 1,2 s (index) y 2,0 → 1,3 s (application);
  - Performance mobile 98 → 100 en las dos páginas.

### H4 — Foto del index en tamaños adaptados y WebP · `1c6bc92`

- **Causa:** la foto se servía como el original de cámara, un JPEG de 1920×1156 y 308 KB, para mostrarse a 576×347 o menos. Era unas cuatro quintas partes del peso del index.
- **Qué se cambió:** un `<picture>` con WebP de 768 y 1152 px (43 y 91 KB), un JPEG de 1152 px de respaldo y `sizes` según la rejilla. Se conservan `width`/`height`, `loading="lazy"` y el `alt`. Las variantes se generaron con `sharp-cli` 6.1.0 vía `npx`.
- **Impacto medido** (final, por auditorías):
  - `total-byte-weight` del index: 376 → **79 KiB** en mobile y 377 → 125 KiB en desktop;
  - `image-delivery-insight`: de 295 a 26 KiB pendientes en mobile y de 274 a 45 KiB en desktop.

  Como estaba previsto, **el impacto es en bytes, no en la puntuación:** la foto va debajo del pliegue, es diferida y no es el LCP.

### R1 — Componente compartido para el contenedor de las tablas · `bd7d084`

- **Causa (refactorización):** las 7 tablas del backoffice repetían su contenedor con scroll horizontal. A 4 de ellas, `/suppliers` y las 3 de `/incidents`, les faltaba el `relative` que evita que los elementos `sr-only` ensanchen la página a 375 px; el test las llevaba como excepciones pendientes.
- **Qué se cambió:**
  - `components/ui/table-scroll.tsx` (`TableScroll`, con `framed` y `className`), que usan las 7 tablas;
  - la lista de excepciones queda vacía;
  - una regla estática exige que `overflow-x-auto` solo esté en el componente.
- **Impacto:** sin cambio visual ni métrico. A 375 px no hay scroll horizontal en `/suppliers`, `/incidents` (con un análisis cargado), `/incident-manager` ni en las 4 páginas de `/inventory`.

## 3. Antes y después (12 casos)

Valores de los JSON: FCP y LCP en segundos, TBT en ms. Antes: 3–4 ejecuciones por caso, la guardada en el JSON ([`audit/before/runs.md`](audit/before/runs.md)). Después: 1 ejecución por caso ([`audit/after/runs.md`](audit/after/runs.md) §3).

### Mobile (412 px en los dos lados: comparación homogénea)

| Página | Perf | A11y | BP | SEO | FCP | LCP | TBT | CLS | Capturas |
|---|---|---|---|---|---|---|---|---|---|
| website · index | 98 → **100** | 100 → 100 | 100 → 100 | 100 → 100 | 1,9 → **0,9** | 2,1 → **1,2** | 15 → 72 | 0 → 0 | [antes](audit/before/website/index/index-mobile.png) · [después](audit/after/website/index/index-mobile.png) |
| website · application | 98 → **100** | 100 → 100 | 100 → 100 | 100 → 100 | 1,9 → **0,9** | 2,0 → **1,3** | 25 → 6 | 0 → 0 | [antes](audit/before/website/application/application-mobile.png) · [después](audit/after/website/application/application-mobile.png) |
| backoffice · login (en frío) | 100 → 99 | 100 → 100 | 100 → 100 | 100 → 100 | 0,8 → 0,8 | 1,7 → 1,6 | 23 → 101 | 0 → 0 | [antes](audit/before/backoffice/login/login-mobile.png) · [después](audit/after/backoffice/login/login-mobile.png) |
| backoffice · incident-manager | 82 → **99** | 100 → 100 | 100 → 100 | 100 → 100 | 0,6 → 0,6 | 1,0 → 1,0 | 24 → 134 | 0,373 → **0** | [antes](audit/before/backoffice/incident-manager/incident-manager-mobile.png) · [después](audit/after/backoffice/incident-manager/incident-manager-mobile.png) |
| backoffice · suppliers | 95 → **99** | 100 → 100 | 100 → 100 | 100 → 100 | 0,6 → 0,6 | 1,1 → 1,0 | 78 → 125 | 0,136 → **0,003** | [antes](audit/before/backoffice/suppliers/suppliers-mobile.png) · [después](audit/after/backoffice/suppliers/suppliers-mobile.png) |
| backoffice · inventory/products | 95 → **99** | 100 → 100 | 100 → 100 | 100 → 100 | 0,6 → 0,7 | 0,9 → 1,0 | 58 → 122 | 0,135 → **0,001** | [antes](audit/before/backoffice/inventory-products/inventory-products-mobile.png) · [después](audit/after/backoffice/inventory-products/inventory-products-mobile.png) |

### Desktop (complementario: 1526 px en el antes y 870 px en el después)

| Página | Perf | A11y | BP | SEO | FCP | LCP | TBT | CLS | Capturas |
|---|---|---|---|---|---|---|---|---|---|
| website · index | 100 → 100 | 100 → 100 | 100 → 100 | 100 → 100 | 0,5 → 0,2 | 0,5 → 0,3 | 0 → 0 | 0 → 0 | [antes](audit/before/website/index/index-desktop.png) · [después](audit/after/website/index/index-desktop.png) |
| website · application | 100 → 100 | 100 → 100 | 100 → 100 | 100 → 100 | 0,5 → 0,2 | 0,5 → 0,3 | 0 → 0 | 0 → 0 | [antes](audit/before/website/application/application-desktop.png) · [después](audit/after/website/application/application-desktop.png) |
| backoffice · login (en frío) | 100 → 100 | 100 → 100 | 100 → 100 | 100 → 100 | 0,2 → 0,2 | 0,4 → 0,4 | 0 → 0 | 0,003 → 0 | [antes](audit/before/backoffice/login/login-desktop.png) · [después](audit/after/backoffice/login/login-desktop.png) |
| backoffice · incident-manager | 100 → 100 | 100 → 100 | 100 → 100 | 100 → 100 | 0,2 → 0,2 | 0,3 → 0,3 | 0 → 0 | 0,032 → 0 | [antes](audit/before/backoffice/incident-manager/incident-manager-desktop.png) · [después](audit/after/backoffice/incident-manager/incident-manager-desktop.png) |
| backoffice · suppliers | 100 → 99 | 100 → 100 | 100 → 100 | 100 → 100 | 0,2 → 0,2 | 0,2 → 0,3 | 0 → 2 | 0,032 → 0,071 | [antes](audit/before/backoffice/suppliers/suppliers-desktop.png) · [después](audit/after/backoffice/suppliers/suppliers-desktop.png) |
| backoffice · inventory/products | 100 → 100 | 100 → 100 | 100 → 100 | 100 → 100 | 0,2 → 0,2 | 0,2 → 0,3 | 0 → 0 | 0,032 → 0,026 | [antes](audit/before/backoffice/inventory-products/inventory-products-desktop.png) · [después](audit/after/backoffice/inventory-products/inventory-products-desktop.png) |

**Cómo leer las dos tablas:**

- **El TBT del backoffice mobile sube** (de 24–78 a 101–134 ms), y por eso su Performance es 99 y no 100. **Es efecto de la CPU de la máquina, no del código:** el `benchmarkIndex` del después es un 35–45 % más bajo que el del antes (§6). El TBT sigue por debajo de 200 ms en todos los casos. El CLS, que es lo que se corrigió, no depende de la CPU.
- **En desktop, el ancho cambia el diseño:**
  - la foto del index pasa a una sola columna;
  - el LCP del index deja de ser el logo y pasa a ser el `h1`;
  - la navegación y los filtros parten línea de otra manera.

  Las cifras desktop sirven para ver que nada se rompe, no para medir la mejora.

## 4. Qué tuvo más impacto y por qué

1. **H2 y H1, en el backoffice mobile.** Eran las únicas métricas fuera de umbral, y el CLS pesa un 25 % en la Performance de Lighthouse 13.
   - **H2** sola llevó `/incident-manager` de 88 a 100 en su medición intermedia.
   - **H1** quitó el 0,1337 común a las tres vistas.

   Las dos atacan la misma causa raíz de fondo: contenido que llega después de pintar sin espacio reservado (la sesión validada en cliente, D10, y un panel con carga propia). Por eso arreglarla en el layout corrige varias vistas a la vez.
2. **H3, en el sitio.** Mayor impacto en los tiempos: FCP de 1,9 a 0,9 s y LCP de 2,1 a 1,2 s en mobile. Quitó un JavaScript de terceros, síncrono, del camino crítico de las 3 páginas. Además fija la versión de Tailwind, que con `@4` en el CDN podía cambiar sin aviso.
3. **H4.** Mayor impacto en bytes: el index pesa un 79 % menos en mobile. Pero no mueve la puntuación, porque la foto no está en el camino del primer pintado.
4. **R1.** Sin impacto en métricas. Su valor es de mantenimiento: la regla del `relative` vive en un solo sitio, y el test impide que vuelva a repetirse.

## 5. Residuales y regresiones menores

Ninguno supera un umbral. Ninguno es una regresión de las correcciones; todos quedan como trabajo futuro, sin aplicar. Detalle en [`audit/after/runs.md`](audit/after/runs.md) §3.4.

- **`/suppliers` desktop, CLS 0,071** (la fila de filtros).
  - **Causa:** cuando llega el listado aparece el contador del directorio; a 870 px de ancho, los filtros pasan a la línea siguiente.
  - **No es de H1:** en el antes no iba sumado al desplazamiento de la cabecera, porque el CLS total desktop era 0,0323, exactamente el de la cabecera. Es el mismo nodo que el residual S5 de mobile (0,0026).
  - **Posible arreglo:** reservar la línea del contador antes de que llegue el listado, o dejar los filtros siempre en su propia línea.
- **`/inventory/products` desktop, CLS 0,026** («Cerrar sesión»).
  - **Causa:** el residual 3 previsto en H1. El hueco del email mide 160 px (`w-40`) y el email real es más ancho, así que el botón se desplaza al llegar la sesión.
  - **Posible arreglo:** dar al email la misma anchura que el hueco (`w-40` con `truncate` y el email completo en `title`).
- **Estos dos dependen del ancho de la ventana.** Con el ancho del antes (1526 px) no se sabe si aparecen, porque no se midió.
- **Imagen del index (H4), 26–45 KiB estimados.**
  - **Causa:** con solo dos anchos en el `srcset`, el navegador toma el inmediatamente superior.
  - **Posible arreglo:** una variante intermedia.
- **TBT del backoffice mobile más alto:** atribuido a la CPU (§3, §6).
- **Login mobile en frío, Performance 100 → 99:** por el TBT (23 → 101 ms) con la misma CPU más lenta. El FCP y el LCP no empeoran (0,8 s y 1,6 s).

## 6. Lo que no se aplicó y por qué

| ID | Qué | Motivo |
|---|---|---|
| S1 | `width`/`height` del logo y `fetchpriority` | Recortado por el usuario. Sin ahorro estimado, y `unsized-images` sigue marcando el logo sin ahorro de CLS. En la medición final (desktop a 870 px), el LCP del index ya no es el logo, sino el `h1` |
| S2 | CSS bloqueante del login (`experimental.inlineCss`) | La skill exige además un *render delay* largo y no lo hay (71 ms). Es un flag experimental y empeora las visitas recurrentes |
| S3 | Polyfills del chunk de Next | Es código del framework (`polyfill-module`), no de la app; quitarlo exigiría intervenir el build |
| S4 | Minificar `validations.js` | 4 KiB y sin ahorro en métricas; en producción Netlify lo sirve comprimido |
| S5 | Desplazamientos residuales de filtros y leyenda | Muy por debajo de 0,1 (ver §5 para el caso de `/suppliers` desktop) |
| R2 | Hook genérico de listados del inventario | Recortado por el usuario para cerrar el ticket. R1 ya cumple el «al menos un componente reutilizable» del brief |
| R3 | Lista de errores por campo de los avisos | Sin impacto en métricas, y tocaría AUTH-02 |
| R4 | Bloque «Cargando…» de los listados | 4 líneas de marcado sin lógica |
| R5 | Cabecera y pie de los 3 HTML del sitio | Compartirlos exigiría inyectarlos con JS (peor SEO y más CLS) o un build (reestructura) |
| N1 | *Render delay* por la espera del guard | D10: cambiarlo exige cookies o middleware, que la arquitectura de AUTH-02 prohíbe. Los LCP cumplen |
| N2 | Hueco FCP→LCP del login | Artefacto de la simulación (en la carga observada coinciden) |
| X1–X4 | Compresión, caché, HTTP/2 y TTFB | Son del servidor local de la medición, no de producción |

## 7. Limitaciones

- **Solo laboratorio:** no hay CrUX ni RUM (local, sin URL pública). Ninguna mejora se presenta como mejora de campo.
- **Servidor local:** compresión, caché, HTTP/2 y TTFB no son los de producción (X1–X4).
- **Simulación:** FCP, LCP, TBT y Speed Index son estimaciones del modelo de Lighthouse; el CLS es el observado.
- **Ejecuciones:** 1 por caso en el después, frente a 3–4 en el antes. Se aceptó porque en el antes la Performance varió ≤ 1 punto entre ejecuciones y el CLS fue idéntico.
- **CPU distinta:** `benchmarkIndex` de 2080–2499 en el después, frente a 3570–3893 en el antes. Afecta al TBT y al trabajo del hilo principal, no al CLS ni a los bytes.
- **Desktop no homogéneo:** ventana de 870 px en el después, frente a 1526 en el antes, sin emulación en ninguno de los dos lados (§3).
- **Mediciones intermedias de una sola ejecución,** y la de H1 con extensiones activas (documentado).
- **Datos de desarrollo:** el ticket 028 pasó a `in_progress` durante la verificación de H2. Cambia dos totales del resumen, no el número de filas ni el CLS.

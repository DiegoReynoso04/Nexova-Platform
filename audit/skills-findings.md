# Hallazgos de las skills `core-web-vitals` y `performance` (F2)

Registro de la ejecución de las dos skills de agente sobre los dos frontends: qué señalan, con qué evidencia, qué código lo causa y qué corrección proponen. Es la evidencia del uso de las skills que pide el brief ([`docs/perf-audit-brief.md`](../docs/perf-audit-brief.md)) y el material de entrada de `AUDIT.md` (F3).

**Aquí no se corrige nada.** Las correcciones se aplican después, una por commit y en el orden de §7. El usuario revisó y aprobó esta lista; sus decisiones y ajustes están en §8.

## 1. Cómo se ejecutaron

| | |
|---|---|
| Skills | `core-web-vitals` y después `performance`, invocadas con la herramienta de skills de Claude Code (2026-10-27). Están en `.claude/skills/` (commit `8871787`), con origen `addyosmani/web-quality-skills@afa8da9` |
| Referencias leídas | `core-web-vitals/references/CLS.md` y `LCP.md` (hay desplazamientos y LCP que analizar). `INP.md` no aplica: no hay ninguna interacción lenta medida y el TBT máximo es de 80 ms (suppliers mobile) |
| Evidencia | Solo los 12 JSON de [`audit/before/`](before/runs.md) (Lighthouse 13.4.1, Chrome 155, commit `fb3cb15`). No se ha vuelto a medir |
| Código | El de `feature/perf-audit` en `8871787`, que es el medido (desde `fb3cb15` solo han cambiado documentación y skills) |

**Desviaciones del flujo de las skills**, decididas antes de F2:

- **Sin datos de campo.** El paso 1 de las skills («Measure before optimizing» y «How it works») es CrUX p75. Aquí no existe: se mide en local, sin URL pública (F0), y `MEASUREMENT.md` («Reading CrUX correctly») trata la falta de CrUX como «no disponible», no como aprobado. Por eso todos los hallazgos son **de laboratorio**. Ninguna corrección podrá presentarse como mejora de campo, como pide la propia skill.
- **Sin traza nueva ni CLI.** El paso 2 (traza con Chrome DevTools MCP) y el fallback de `MEASUREMENT.md` (CLI de Lighthouse o PageSpeed) no se usan: toda medición es con el panel Lighthouse de DevTools y la hace el usuario. Lo que la skill buscaría en una traza se ha sacado de las auditorías del JSON: `layout-shifts`, `cls-culprits-insight`, `lcp-breakdown-insight`, `render-blocking-insight` y `fullPageScreenshot.nodes` para la geometría.
- **Causas sin confirmar en traza.** Cuando una causa se deduce del código y de la geometría, pero no aparece en el JSON (Lighthouse 13 no trae `cause`/`extra` en ningún desplazamiento), se marca como **causa probable**. La confirmación es la medición *after* de la misma URL.

**Criterio de clasificación** ([`runs.md` §3](before/runs.md)). Una corrección es **requerida** si se da (a) o (b):

- **(a)** una métrica medida incumple su umbral: Performance < 90, LCP > 2,5 s, CLS > 0,1 o TBT > 200 ms;
- **(b)** es una auditoría fallida con ahorro estimado que la skill señala como causa.

Todo lo demás es **sugerencia**.

## 2. Resumen

| ID | Frontend | Qué | Evidencia principal | Clasificación | Riesgo |
|---|---|---|---|---|---|
| **H1** | backoffice | La cabecera crece cuando aparece la navegación con sesión y empuja `main` | CLS 0,1337 en las 3 vistas mobile; 0,032 en las 3 desktop | **Requerida** (a) | Medio-bajo, toca AUTH-02 |
| **H2** | backoffice | El panel de resumen de `/incident-manager` crece al llegar los datos y empuja el listado | CLS +0,2344 en incident-manager mobile (total 0,373, Perf 82) | **Requerida** (a) | Bajo |
| **H3** | website | Play CDN de Tailwind: JavaScript síncrono que bloquea el render | `render-blocking-insight`: hasta 1150 ms en FCP/LCP (mobile) | **Requerida** (b) | Medio (visual) |
| **H4** | website | Foto de 1920×1156 (308 KB) mostrada a 576×347 | `image-delivery-insight`: 274–295 KiB | **Requerida** (b), caso límite (§8) | Bajo |
| S1 | website | `logo.svg` sin `width`/`height` y, en desktop, LCP sin `fetchpriority` | `unsized-images`, `lcp-discovery-insight`, sin ahorro | Sugerencia; se aplica tras H3 si sigue teniendo sentido (§8) | Muy bajo |
| S2 | backoffice | CSS bloqueante en el login en frío | `render-blocking-insight`: 150 ms (solo mobile, en frío) | Sugerencia, caso límite (§8) | Medio (flag experimental) |
| S3 | backoffice | Polyfills y JS sin usar del chunk del framework | `legacy-javascript-insight` 13–14 KiB, `unused-javascript` 26 KiB; FCP/LCP 0 | Sugerencia, no accionable | — |
| S4 | website | `validations.js` sin minificar | `unminified-javascript`: 4 KiB; sin ahorro | Sugerencia | — |
| S5 | backoffice | Desplazamientos residuales (filtros, leyenda del stock) | 0,0052 / 0,0026 / 0,0014 | Sugerencia | — |
| N1 | backoffice | *Render delay* del LCP por la espera del guard | 166–206 ms (mobile) | Documentado, no se corrige (D10) | — |
| N2 | backoffice | Hueco FCP→LCP de 900 ms en el login mobile | Solo en la simulación; observado FCP = LCP = 78 ms | Artefacto de laboratorio | — |
| X1–X4 | ambos | Compresión, caché, HTTP/2 y TTFB | Servidor local | Descartados (§6) | — |

## 3. Correcciones requeridas

### H1 — La cabecera del backoffice crece al validarse la sesión (CLS)

**Skill:**

- `core-web-vitals` → *CLS* y `references/CLS.md` → «Handle dynamic content deliberately»: no insertar contenido sobre el visible sin reservar su espacio. La *Verification checklist* pide además «async components have stable containers».
- `CLS.md` advierte de que el nodo desplazado puede ser la víctima («the element that moved may be the victim of content inserted above it»). Es el caso: Lighthouse señala `main`, pero quien crece es la cabecera.

**Evidencia:**

| JSON | Auditoría | Elemento | Puntuación |
|---|---|---|---|
| `backoffice/suppliers/suppliers-mobile.json` | `layout-shifts` | `body.flex > main.mx-auto` | 0,1336942940441483 |
| `backoffice/inventory-products/inventory-products-mobile.json` | `layout-shifts` | `body.flex > main.mx-auto` | 0,1336942940441483 |
| `backoffice/incident-manager/incident-manager-mobile.json` | `layout-shifts` | `body.flex > main.mx-auto` | 0,1336942940441483 |
| `backoffice/incident-manager/incident-manager-desktop.json` | `layout-shifts` | `body.flex > main.mx-auto` | 0,032271 |
| `backoffice/suppliers/suppliers-desktop.json` | `layout-shifts` | `body.flex > header.border-b > div.mx-auto` | 0,032270 |
| `backoffice/inventory-products/inventory-products-desktop.json` | `layout-shifts` | `body.flex > header.border-b > div.mx-auto` | 0,032270 |

- **Geometría** (`fullPageScreenshot.nodes`). `main` empieza en `top: 170` en las tres vistas mobile y en `top: 134` en las tres desktop. En el login, sin navegación con sesión, empieza en `top: 53`. Esos 53 px son la cabecera solo con la marca: `py-4` (32 px) + una línea `text-sm` (20 px) + el borde (1 px).
- **La cuenta cuadra en mobile.** Viewport de 412×823, desplazamiento de 117 px (de 53 a 170):
  - fracción de distancia: 117 / 823 = 0,142;
  - fracción de impacto: `main` ocupa de 53 a 823 antes y de 170 a 823 después, así que la unión es 770 / 823 = 0,936;
  - producto: 0,936 × 0,142 ≈ **0,133**, la cifra medida.

  La puntuación idéntica en las tres vistas, con 16 decimales, encaja con una causa común al layout y ajena a cada vista.
- **Desktop: el mismo evento.** La cabecera pasa de 53 a 134 px. En el JSON, el nodo atribuido varía (`main` o el contenedor de la cabecera), pero la puntuación coincide en seis decimales. Por debajo del umbral, pero la misma corrección lo elimina.

**Código implicado:**

- [`uis/backoffice/app/layout.tsx:20-33`](../uis/backoffice/app/layout.tsx): la cabecera, con `<AccountNav />`, está en el flujo normal, encima de `main`.
- [`uis/backoffice/components/auth/account-nav.tsx:24-55`](../uis/backoffice/components/auth/account-nav.tsx):
  - con `authenticated` pinta 8 elementos (6 enlaces, el email y «Cerrar sesión»);
  - en `initializing` y `checking` devuelve `null` (línea 55).
- [`uis/backoffice/hooks/use-auth-session.ts:68`](../uis/backoffice/hooks/use-auth-session.ts), `:75` y `:188-191`: en el servidor y durante la hidratación el token es `undefined` (`initializing`). Con token, el estado es `checking` hasta que `GET /auth/me` responde.

**Causa probable.** El HTML del servidor, y la primera pintura, llevan la cabecera de 53 px. Cuando `/auth/me` confirma la sesión, `AccountNav` pinta la navegación completa. En 412 px, y también en los 896 px de `max-w-4xl`, la navegación ocupa varias líneas: la cabecera crece 117 px en mobile y 81 px en desktop, y empuja todo `main` hacia abajo. Es la cascada del guard (D10), vista desde la cabecera y no desde `main`.

**Corrección propuesta.** Reservar el espacio de la navegación con sesión mientras la sesión se comprueba en una ruta protegida:

- **Cuándo:** en `initializing` y `checking`, y solo cuando `routeAccess(pathname, status) === 'wait'` ([`lib/auth-routes.ts:50`](../uis/backoffice/lib/auth-routes.ts)).
- **Cómo:**
  - `AccountNav` pinta la misma navegación, pero no visible y no interactiva: `invisible`, `aria-hidden` e `inert`;
  - **condición del usuario (revisión de F2):** la navegación reservada no usa `Link` ni `href`. Cada entrada es un `<span>` con las mismas clases y el mismo texto. Motivo: `NavLink` usa `next/link`, y en producción Next precarga los enlaces visibles en el viewport. Con `span` no hay precargas de rutas protegidas durante la carga ni enlaces protegidos en el HTML sin sesión;
  - en lugar del email, un marcador de ancho parecido;
  - como `usePathname` y el estado `initializing` existen también en el servidor, el HTML inicial ya trae la cabecera con su altura final.
- **Donde no cambia nada:** en las rutas públicas (`/login`, `/register`, `/forgot-password`) se mantiene lo de hoy.
- **Para no duplicar el marcado:** la lista de entradas se saca a una única pieza interna de `account-nav.tsx`, que usan los dos estados, con una prop que elige entre enlace (`NavLink`) y `span`. Así sigue pasando el test estático que exige un solo enlace «Inventario» ([`tests/production-source.test.mjs:170-175`](../uis/backoffice/tests/production-source.test.mjs)).

**Alternativas descartadas:**

- **Un `min-height` fijo en la cabecera por breakpoint:** frágil, porque la altura depende de cuántas líneas ocupe la navegación, del ancho y del email.
- **Mostrar los enlaces protegidos antes de validar la sesión:** contradice AUTH-02 («sin sesión, solo acceso y registro»).
- **Un menú plegable en mobile:** es rediseñar la cabecera, y el brief prohíbe reestructurar.

**Riesgo:**

- **Reestructuración:** ninguna. Es un componente; el layout, el guard y la sesión no cambian.
- **AUTH-02, medio-bajo:**
  - **La espera de `/auth/me` sigue igual:** el guard no se toca, así que D10 se respeta.
  - **Sin sesión no se expone nada:** ningún enlace protegido es visible, enfocable ni anunciado. Hay que comprobar con el árbol de accesibilidad que `aria-hidden` + `inert` lo ocultan.
  - **Residual 1, token caducado o inválido en una ruta protegida:** el hueco reservado se cierra al pasar a `anonymous`, justo antes de la redirección a `/login`. Ese caso no se mide.
  - **Residual 2, error de red al validar:** la navegación desaparece y la cabecera encoge.
  - **Residual 3, email más largo que el marcador:** puede cambiar el número de líneas en mobile y dejar un desplazamiento pequeño.
- **Verificación:**
  - la fila de `uis/backoffice` de `AGENTS.md`;
  - el recorrido AUTH-02 en el navegador: login correcto e incorrecto, redirección sin token y tras un 401, y logout;
  - en la pestaña Network, con el build de producción: ninguna precarga de las rutas protegidas antes de que `/auth/me` responda.

**Efecto esperado** (estimación, no medición). Desaparece el desplazamiento de `main`:

- suppliers mobile, de 0,136 a ≈ 0,003;
- inventory/products mobile, de 0,135 a ≈ 0,001;
- incident-manager mobile, de 0,373 a ≈ 0,24, todavía por encima del umbral (falta H2);
- las tres vistas desktop, de 0,032 a ≈ 0.

La estimación resta componentes, y el CLS de Lighthouse es la ventana de sesión máxima. Las cifras reales salen de volver a medir.

### H2 — El resumen de `/incident-manager` crece al llegar los datos (CLS)

**Skill:**

- `core-web-vitals` → `references/CLS.md` → «Handle dynamic content deliberately»: reservar un contenedor estable antes de que llegue el contenido;
- *Verification checklist* → «async components have stable containers».

**Evidencia:**

- **Desplazamiento:** `backoffice/incident-manager/incident-manager-mobile.json` → `layout-shifts`: `body.flex > main.mx-auto > section.flex` (`<section aria-labelledby="incident-list-heading">`), **0,2344**. Es un evento distinto del de H1, que también aparece en ese JSON (0,1337).
- **Rendimiento:** `cls-culprits-insight` falla (puntuación 0). El caso tiene Performance **82** y CLS **0,373**, los dos fuera de umbral.
- **Geometría final:** la sección del listado empieza en `top: 1048`, por debajo de los 823 px del viewport. Antes de desplazarse estaba dentro de la pantalla.
- **En desktop no aparece** este desplazamiento (`incident-manager-desktop.json`, solo el de H1).

**Código implicado:**

- [`uis/backoffice/components/incident-manager/incident-board-view.tsx:40-42`](../uis/backoffice/components/incident-manager/incident-board-view.tsx): el panel de resumen va justo encima de la sección del listado.
- [`uis/backoffice/components/incident-manager/incident-summary-panel.tsx`](../uis/backoffice/components/incident-manager/incident-summary-panel.tsx):
  - `:40-45`: mientras carga, el panel es una sola fila «Cargando resumen…», de unos 60 px;
  - `:47-56`: al llegar los datos, pinta una rejilla `grid-cols-1 … lg:grid-cols-4` con 4 listas de 4, 8, 3 y 4 filas. En mobile van apiladas, así que son 19 filas y 4 títulos;
  - `:25`: además aparece «Total de incidencias».

**Causa probable.** En mobile, el panel pasa de una fila a cuatro listas apiladas y empuja la sección del listado varios cientos de píxeles. En desktop (`lg:grid-cols-4`) la diferencia de altura es mucho menor y no se registró desplazamiento. No se puede confirmar sin traza si es por esa menor altura o por el orden en que llegan las dos respuestas; la medición *after* lo resuelve.

**Corrección propuesta.** Mientras `summary === null` y el panel carga, pintar la misma rejilla con las 4 listas y sus filas desde el vocabulario, con un marcador («—», `aria-hidden`) en lugar de cada número:

- `INCIDENT_STATUSES`, `INCIDENT_CATEGORIES`, `INCIDENT_ORIGINS` e `INCIDENT_BRANCHES`, de [`types/incident-manager.ts:15-27`](../uis/backoffice/types/incident-manager.ts);
- el aviso «Cargando resumen…» se mantiene como estado accesible;
- se reserva también la línea de «Total de incidencias».

La altura final es determinista: el contrato garantiza exactamente una entrada por valor del vocabulario ([`services/normalizers.ts:455-467`](../uis/backoffice/services/normalizers.ts), `readCounts`).

**Riesgo:**

- **Reestructuración y AUTH-02:** ninguno.
- **Se mantiene la carga y el error propios del resumen** (fallo aislado, `uis/backoffice/CLAUDE.md`).
- **Residual:** si el resumen falla en la primera carga, el aviso de error tiene otra altura y queda un desplazamiento en ese caso, que no se mide.
- **Verificación:** la fila de `uis/backoffice`, más el recorrido de `/incident-manager` en el navegador. En particular, el fallo aislado del resumen y el cambio de estado que recarga el resumen.

**Efecto esperado** (estimación). Tras H1 y H2, el CLS de incident-manager mobile queda en el residual de los filtros (≈ 0,005, S5). La Performance debería subir, porque el CLS pesa un 25 % en la puntuación de Lighthouse 13; no se adelanta cifra.

### H3 — El Play CDN de Tailwind bloquea el render (LCP/FCP)

**Skill:**

- `core-web-vitals` → *Common LCP issues* §2 («Render-blocking resources») y la *LCP optimization checklist* («No render-blocking JavaScript in `<head>`»);
- `references/LCP.md` → «Defer JavaScript»;
- `performance` → *JavaScript optimization* («Parser-blocking (avoid)») y *Third-party scripts*.

**Evidencia:**

| JSON | Auditoría | Ahorro estimado |
|---|---|---|
| `website/index/index-mobile.json` | `render-blocking-insight` (puntuación 0) | FCP 1150 ms, LCP 1150 ms |
| `website/application/application-mobile.json` | `render-blocking-insight` (0) | FCP 1100 ms, LCP 1100 ms |
| `website/index/index-desktop.json` | `render-blocking-insight` (0) | FCP 300 ms, LCP 0 |
| `website/application/application-desktop.json` | `render-blocking-insight` (0) | FCP 300 ms, LCP 300 ms |
| `website/index/index-*.json` | `unused-javascript` (0) | 21 KiB sin usar de 56 KiB; FCP 150 ms (mobile), FCP/LCP 50 ms (desktop) |
| los 4 del sitio | `cache-insight` (0,5) | 6 KiB (solo el script del CDN, TTL de 7 días) |

Aparte de los ahorros, en los 4 JSON del sitio:

- `network-dependency-tree-insight` muestra la cadena documento → `cdn.jsdelivr.net`, sin `preconnect`;
- el LCP mobile (2,1 s en index y 2,0 s en application) es el más alto de todos los casos medidos.

**Código implicado:**

- [`uis/website/index.html:18`](../uis/website/index.html), [`uis/website/application.html:12`](../uis/website/application.html) y [`uis/website/404.html:12`](../uis/website/404.html): `<script src="https://cdn.jsdelivr.net/npm/@tailwindcss/browser@4"></script>` en el `<head>`, sin `defer`;
- la versión no está fijada: `@4` resolvió a la 4.3.3 en F1.

**Causa probable.** El Play CDN de Tailwind es JavaScript que genera el CSS en el navegador, así que tiene que ejecutarse antes de pintar. Si se le pusiera `defer`, la página se pintaría sin estilos y luego se recolocaría (FOUC y CLS). El navegador no puede pintar nada hasta que:

1. abre la conexión con un tercer origen;
2. descarga 57 KB;
3. los ejecuta;
4. escanea el DOM;
5. inyecta el CSS.

Con el throttling de mobile, eso son 1,1–1,15 s del LCP estimado.

**Corrección propuesta: D3**, ya aprobada en F0:

- **El CSS:**
  - Tailwind precompilado con su CLI, en la versión fijada `npx @tailwindcss/cli@4.3.3`, la misma que se midió;
  - salida minificada a un archivo local, enlazado con `<link rel="stylesheet">` en las 3 páginas.
- **Sin dependencias:** no se añade ningún `package.json` ni dependencia.
- **Versionado:** el CSS generado se versiona, porque Netlify publica `uis/website` sin build.
- **Qué escanea el CLI:** también `src/js/*.js`, por las clases que añade el JavaScript (`hidden`, `border-red-700`, `border-slate-400`, el HTML de `formStatus` en `validations.js`).
- **Documentación:** el comando va en un `uis/website/README.md` nuevo, que se crea en el commit de H3. Se descarta `uis/README.md` por tres motivos:
  - la regla del monorepo pide un README por app (`.agents/rules/monorepo-structure.md`, «Cada app/servicio/agente nuevo lleva su propia subcarpeta con README»), y el sitio es la única app de `uis/` que no lo tiene;
  - el paso de generación del CSS solo afecta al sitio: qué archivos escanea, la versión fijada y cuándo regenerarlo. Es documentación de la app, no del índice de interfaces;
  - `uis/README.md` sigue siendo el índice. Su fila del sitio («Play CDN, no build step») se corrige en ese mismo commit y enlaza al README nuevo.

**Riesgo:**

- **Reestructuración:** no. El sitio sigue siendo HTML estático, sin build en el despliegue.
- **AUTH-02:** no aplica.
- **Visual: medio.** Una clase que el CLI no detecte desaparecería del CSS. Por eso D3 exige comparar antes y después en desktop y a 375 px, incluidos el menú móvil abierto y los estados de error y de éxito del formulario.
- **Mantenimiento:** cualquier clase nueva obliga a regenerar el CSS.
- **Bloqueo residual:** el CSS local seguirá bloqueando el render, como todo CSS. Pero es del mismo origen, mucho más pequeño y no ejecuta nada. Inlinearlo solo se plantearía si la traza lo justificara (`LCP.md`: «inline only proven critical CSS»).

### H4 — La foto del index se sirve a 1920×1156 para mostrarse a 576×347

**Skill:**

- `performance` → *Image optimization*: «Format selection» (WebP o AVIF para fotos) y «Responsive images» (`srcset`/`sizes`, `<picture>`);
- `core-web-vitals` → *LCP optimization checklist* («LCP image optimized (WebP/AVIF, correct size)»). Aquí la imagen no es el LCP.

**Evidencia:**

- `website/index/index-desktop.json` → `image-delivery-insight` (puntuación 0,5): `src/img/ambiente-trabajo-nexova.jpg`, 1920×1156 mostrada a 576×347, **274 KiB** de ahorro estimado.
- `website/index/index-mobile.json` → la misma auditoría: mostrada a 380×229, **295 KiB**.
- En los dos, `metricSavings` FCP/LCP 0.
- `total-byte-weight`: 377 KiB en desktop y 376 KiB en mobile. La foto (308 KB) es unas cuatro quintas partes de la página.

**Código implicado:** [`uis/website/index.html:219-224`](../uis/website/index.html). La foto tiene `width="1920" height="1156"` (por eso no causa CLS) y `loading="lazy"` (está debajo del pliegue, así que no es el LCP), pero no tiene `srcset` ni formato moderno. El archivo es [`uis/website/src/img/ambiente-trabajo-nexova.jpg`](../uis/website/src/img/ambiente-trabajo-nexova.jpg), de 308 212 bytes.

**Causa.** Se sirve el original de cámara, sin redimensionar ni recomprimir, a cualquier ancho de pantalla.

**Corrección propuesta: D4**, en una fase de corrección, con `npx sharp-cli@<versión fija>` puntual y sin añadir dependencias:

- **Variantes:** generar 2 anchos, 768 y 1152 px. Cubren 576 px CSS a DPR 2 y 380 px CSS a DPR 1,75, que es el del JSON mobile.
- **Formatos:** WebP más un JPEG recomprimido de respaldo.
- **Marcado:** servirlas con `<picture>`, `srcset` y `sizes` según la rejilla (`lg:grid-cols-2`).
- **Se conservan** `width`/`height` (la proporción 1920:1156), `loading="lazy"`, `decoding="async"` y el `alt`.

**Riesgo:**

- **Reestructuración:** ninguna. Es una imagen y su marcado.
- **Calidad visual:** se revisa a simple vista en desktop y en mobile.
- **Efecto esperado:** solo sobre los bytes (`image-delivery-insight`, `total-byte-weight`). No se espera cambio en Performance ni en LCP, porque la imagen es diferida y no es el LCP.

## 4. Sugerencias (no se aplican salvo que el usuario lo decida)

### S1 — `logo.svg` sin dimensiones y sin prioridad como LCP de desktop

**Skill:**

- `core-web-vitals` → *Framework quick fixes* / `CLS.md` → «Reserve media space» (`width`/`height` en `<img>`);
- *Common LCP issues* §3 («Prefer a discoverable `<img>` with `fetchpriority="high"`»).

**Evidencia:**

- `unsized-images` (0,5) en los 4 JSON del sitio, con `metricSavings` CLS 0. El CLS del sitio es 0.
- `website/index/index-desktop.json` → `lcp-discovery-insight` (0): el LCP es `img.h-10` (`src/img/logo.svg`) sin `fetchpriority=high`, con ahorro LCP 0.
- `lcp-breakdown-insight`: *load delay* de 44 ms y *render delay* de 88 ms.

**Código:** [`uis/website/index.html:70`](../uis/website/index.html), [`application.html:28`](../uis/website/application.html) y [`404.html:35`](../uis/website/404.html): `<img src="src/img/logo.svg" alt="Nexova" class="h-10 w-auto" />`. El SVG declara `width="220" height="56"` ([`src/img/logo.svg`](../uis/website/src/img/logo.svg)).

**Propuesta:**

- añadir `width="220" height="56"`, que la clase `h-10 w-auto` sigue escalando a 40 px de alto;
- añadir `fetchpriority="high"` en el index.

**Por qué es sugerencia:** las dos auditorías no tienen ahorro estimado y ninguna métrica falla.

**Cuándo decidirlo:** después de H3. Al quitar el script del CDN, el elemento LCP de desktop puede cambiar.

### S2 — CSS bloqueante en el login en frío del backoffice

**Skill:** `core-web-vitals` → *Common LCP issues* §2 y `references/LCP.md` → *Common issues*, fila «Render-blocking CSS». Esa fila pide como evidencia «`RenderBlocking` insight **and long render delay**».

**Evidencia:**

- `backoffice/login/login-mobile.json` → `render-blocking-insight` (0): `_next/static/chunks/3041c5xfhjw05.css` (4,8 KB), con ahorro FCP/LCP de 150 ms.
- Con sesión (casos 5–8, 11 y 12), el CSS viene de la caché y la auditoría no tiene ahorro.
- `lcp-breakdown-insight` del login mobile: *render delay* de solo 71 ms.

**Código:** el CSS global de Next ([`uis/backoffice/app/globals.css`](../uis/backoffice/app/globals.css), importado en `app/layout.tsx:7`).

**Propuesta posible:** `experimental.inlineCss` en `next.config.ts`, documentado en `node_modules/next/dist/docs/…/inlineCss.md`.

**Por qué es sugerencia:**

- la skill condiciona la corrección a un *render delay* largo, y no lo hay;
- el LCP del login (1,7 s) cumple;
- el flag es experimental y global;
- la propia documentación de Next lo desaconseja cuando los visitantes recurrentes son comunes. Es el caso del backoffice, que el personal usa a diario: con inline, cada carga volvería a descargar el CSS.

Caso límite: ver §8.

### S3 — Polyfills y JavaScript sin usar del chunk del framework

**Skill:** `performance` → *How it works*, paso 3: «Inspect and change only the code or assets connected to measured bottlenecks».

**Evidencia:**

- `legacy-javascript-insight` (0,5) en los 8 JSON del backoffice: `_next/static/chunks/0zutzion2550z.js`, 13–14 KiB, con FCP/LCP 0. Las señales son `Array.prototype.at`, `flat`, `flatMap`, `Object.fromEntries`, `Object.hasOwn`, `String.prototype.trimStart` y `trimEnd`.
- `unused-javascript` (0,5) en el login, con el mismo chunk: 26 KiB sin usar de 72 KiB, con FCP/LCP 0.

**Código:** ninguno de la app. El chunk empieza con el `polyfill-module` del propio Next.js:

- en `uis/backoffice/.next/static/chunks/0zutzion2550z.js`, el primer módulo es `"trimStart"in String.prototype||(…)`, igual que `node_modules/next/dist/build/polyfills/polyfill-module.js`;
- `package.json` no define `browserslist`, así que se aplican ya los destinos modernos por defecto de Next 16 (Chrome/Edge/Firefox 111, Safari 16.4; `node_modules/next/dist/docs/03-architecture/supported-browsers.md`).

**Por qué es sugerencia no accionable:**

- no tiene ahorro en métricas;
- quitarlo obligaría a intervenir el build del framework, lo que va contra el brief («no reestructures»).

### S4 — `validations.js` sin minificar

**Evidencia:** `unminified-javascript` (0,5) en `website/application/application-*.json`: `src/js/validations.js`, 12 KB, 4 KiB recuperables, sin ahorro en métricas.

**Propuesta posible:** minificar con una herramienta puntual vía `npx`.

**Por qué es sugerencia:**

- no tiene ahorro en métricas;
- en producción Netlify lo sirve comprimido (X1);
- añadiría otro paso generado que mantener.

### S5 — Desplazamientos residuales en las vistas con datos

**Evidencia** (`layout-shifts`):

| JSON | Elemento | Puntuación |
|---|---|---|
| `incident-manager-mobile.json` | `div[role="group"][aria-label="Filtros del listado de incidencias"]` | 0,0052 |
| `suppliers-mobile.json` | `div[role="group"][aria-label="Filtros del directorio"]` | 0,0026 |
| `inventory-products-mobile.json` | `p.text-xs` («Nivel de stock: …») | 0,0014 |
| `login-desktop.json` | `main.mx-auto` (aparece la navegación sin sesión) | 0,003 |

**Código:**

- [`components/incident-manager/incident-filters.tsx:29`](../uis/backoffice/components/incident-manager/incident-filters.tsx);
- [`components/suppliers/supplier-filters.tsx:33`](../uis/backoffice/components/suppliers/supplier-filters.tsx);
- [`components/inventory/asset-list-view.tsx:41`](../uis/backoffice/components/inventory/asset-list-view.tsx);
- [`components/auth/account-nav.tsx:46-53`](../uis/backoffice/components/auth/account-nav.tsx).

**Causa probable:** reflujo de la fila de filtros, o de la leyenda, cuando aparece el contador o el contenido de al lado.

**Por qué es sugerencia:** tras H1 y H2, cada una queda muy por debajo de 0,1.

## 5. Documentados, sin corrección

### N1 — *Render delay* del LCP por la espera del guard (D10)

**Evidencia:** en `lcp-breakdown-insight`, el *render delay* va de 166 a 206 ms en las vistas mobile con sesión:

- incident-manager, 166 ms;
- suppliers, 206 ms;
- inventory/products, 170 ms.

En las tres, el LCP es un párrafo de la página (`p.text-sm`), no una imagen.

**Skill:** `references/LCP.md` → *Common issues*, «Client-rendered LCP»: «LCP element absent from initial HTML and render delay dominates».

**Código:**

- [`components/auth/auth-guard.tsx:30`](../uis/backoffice/components/auth/auth-guard.tsx) y `:53-58`: hasta que `GET /auth/me` confirma la sesión, `main` solo lleva «Comprobando la sesión…», y los `children` (también el `<h1>` y el párrafo, que son de Server Components) no se pintan;
- [`hooks/use-auth-session.ts:188-191`](../uis/backoffice/hooks/use-auth-session.ts): en el servidor no hay token.

**Decisión:** D10. La cascada se documenta como causa y no se corrige: cambiarla exigiría otra estrategia de sesión (cookies o middleware), que `uis/backoffice/CLAUDE.md` prohíbe. Además, todos los LCP cumplen (el máximo es 1,1 s). H1 ataca su efecto en el CLS sin tocar la cascada.

### N2 — Hueco FCP→LCP del login mobile en frío: artefacto de la simulación

**Evidencia** (`backoffice/login/login-mobile.json`, [`runs.md` §5.4](before/runs.md)):

- **Simulado:** FCP 757 ms y LCP 1657 ms, un hueco de 900 ms.
- **Observado** (sin throttling): FCP = LCP = **78 ms**, el mismo instante.
- **Variación entre ejecuciones:** el LCP simulado cambió (2,2 / 2,1 / 1,7 / 1,7 s) con el FCP fijo en 0,8 s.
- **Elemento LCP:** un párrafo de texto que viene en el HTML del servidor. `/login` es una ruta pública y el guard la pinta en cualquier estado ([`lib/auth-routes.ts:52-54`](../uis/backoffice/lib/auth-routes.ts)).

**Skill:**

- `performance/references/MEASUREMENT.md` → «Repeatable lab comparisons»: «Use metric values as the evidence»;
- `core-web-vitals` → *Measurement sources*: no comparar una cifra de laboratorio suelta como si fuera una muestra real.

**Conclusión (probable):**

- el modelo de simulación de Lighthouse estima el LCP con más peticiones y más trabajo de CPU que el FCP, entre ellas los chunks JS de Next (el de 72 KiB tiene una tarea larga de 96 ms en `long-tasks`);
- de ahí el hueco y su variación;
- en la carga real, el párrafo se pinta con la primera pintura.

No hay nada que corregir en la página. La única parte real del bloqueo es el CSS de S2 (150 ms). El LCP cumple el umbral en todas las ejecuciones.

## 6. Descartados: artefactos del servidor local

Las dos skills recomiendan lo mismo en *Critical rendering path → Server response* (`performance`) y *Common LCP issues* §1 (`core-web-vitals`): compresión, HTTP/2, caché y TTFB < 800 ms. Aquí lo que se mide es el servidor local de la medición, no el de producción, así que no se corrige en `uis/serve-website.mjs` ni en `next start`:

| ID | Qué | Evidencia | Por qué se descarta |
|---|---|---|---|
| X1 | Compresión | `document-latency-insight` (0,5) en los 4 JSON del sitio: «No compression applied», 10 KiB (index) y 14 KiB (application), sin ahorro en métricas | `serve-website.mjs` no comprime; en producción el sitio lo sirve Netlify |
| X2 | Caché | `cache-insight` (0,5) solo marca el script del CDN; los archivos locales quedan fuera porque el servidor envía `Cache-Control: no-store` | Política del servidor local. El script del CDN desaparece con H3 |
| X3 | HTTP/2 | `modern-http-insight` pasa (localhost), pero el servidor solo habla HTTP/1.1 | El protocolo lo da la plataforma de despliegue |
| X4 | TTFB | `server-response-time` de 1–3 ms en los 12 casos; en el `lcp-breakdown-insight`, el TTFB es de 4–7 ms | Muy por debajo de 800 ms y nada representativo de producción |

Tampoco se tratan:

- `bf-cache` en incident-manager desktop: «The cache was intentionally cleared», que Lighthouse marca como *Not actionable*;
- `network-dependency-tree-insight`: informativa. En el sitio se resuelve con H3; en el backoffice es la cadena documento → CSS propia de Next.

## 7. Orden propuesto de correcciones

**Orden aprobado por el usuario (revisión de F2):** H1 → H2 → H3 → H4 → S1 → R1 → R2 → medición final.

**Plan final (decisión del usuario, 2026-10-28):** H1 → CRLF → H2 → H3 → H4 → R1 → medición final.

- **S1 y R2:** recortados, quedan documentados como no aplicados.
- **Mediciones intermedias:** solo tras H1 y H2.
- **H3, H4 y R1:** se aplicaron seguidos, cada uno con su commit y su validación.
- **Medición final:** los 12 casos con 1 ejecución por caso.

Primero lo que incumple umbral (criterio a), en el backoffice. Después lo que solo cumple el criterio b, en el sitio. Las condiciones de medición están en [`audit/after/runs.md`](after/runs.md) §1:

- el backoffice siempre desde PowerShell;
- una ventana sin extensiones;
- el mismo ancho de ventana que en el antes. Esta regla no se cumplió en la final desktop (870 frente a 1526 px; ver §3 de ese archivo).

| Orden | Paso | Commit | Medición | Resultado |
|---|---|---|---|---|
| 1 | **H1**: espacio reservado de la navegación con sesión | `4e23d91` | Intermedia: `/suppliers` e `/incident-manager` · mobile | Desaparece el desplazamiento de `main` (0,1337): suppliers mobile CLS 0,136 → 0,003; incident-manager 0,373 → 0,240 |
| — | Contrato del inventario con CRLF | `126d067` | — | `node:test` en verde |
| 2 | **H2**: espacio reservado del panel de resumen | `4039279` | Intermedia: `/incident-manager` · mobile | Desaparece el 0,2344 (y el 0,0052 de los filtros): CLS 0, Performance 100 |
| 3 | **H3**: Tailwind precompilado (D3) | `5823cf7` | Final, por auditorías | Sin el script del CDN en `render-blocking-insight`; FCP mobile 1,9 → 0,9 s y LCP 2,1 → 1,2 s en el index |
| 4 | **H4**: foto en tamaños adaptados y WebP (D4) | `1c6bc92` | Final, por auditorías | `total-byte-weight` del index mobile 376 → 79 KiB; `image-delivery-insight` 295 → 26 KiB (residual por los dos anchos del `srcset`) |
| 5 | **S1** | — | — | No aplicado (recortado) |
| 6 | **R1**: `components/ui/table-scroll.tsx` | `bd7d084` | Final | Sin regresión |
| 7 | **R2** | — | — | No aplicado (recortado) |
| 8 | **Medición final** | — | 12 casos, 1 ejecución, capturas y JSON en `audit/after/<app>/<página>/` | [`REPORT.md`](../REPORT.md) |

- **Orden de H1 y H2.** H1 primero porque afecta a las tres vistas y, sin él, H2 no basta para que incident-manager baje de 0,1.
- **El sitio después.** No incumplía ningún umbral. Sus dos correcciones eran requeridas por el criterio (b).

S1–S5 no se aplican.

## 8. Decisiones del usuario sobre esta lista (revisión de F2)

1. **H4 sigue como requerida, en último lugar** de las correcciones de las skills. `REPORT.md` dirá que su impacto es en bytes, no en la puntuación.
   - **A favor:** cumple el criterio (b) al pie de la letra (auditoría fallida, 274–295 KiB de ahorro, y la sección *Image optimization* de `performance` prescribe exactamente esta corrección). D4 la condicionaba a eso.
   - **En contra:** el paso 3 de *How it works* limita los cambios a cuellos de botella medidos, y su `metricSavings` es 0.
2. **S2 sigue como sugerencia**, por los motivos de §4: la skill (`LCP.md`) exige además un *render delay* largo y hay 71 ms; el flag de Next es experimental y empeora las visitas recurrentes.
3. **El diseño de H1 se aprueba con una condición:** la navegación reservada se pinta con `<span>`, sin `Link` ni `href`, para que no haya precargas de rutas protegidas. Se verifica en la pestaña Network (§3, H1).
4. **H3:** el comando del CSS se documenta en un `uis/website/README.md` nuevo (§3, H3).
5. **S1** se aplicaría después de H3, con su propio commit, si seguía teniendo sentido. **Después, el usuario lo recortó (2026-10-28)**, igual que R2.

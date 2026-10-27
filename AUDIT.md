# AUDIT — Auditoría de rendimiento de los dos frontends

Análisis inicial de la auditoría de rendimiento que pide el brief ([`docs/perf-audit-brief.md`](docs/perf-audit-brief.md)). Recoge:

- las puntuaciones iniciales de Lighthouse;
- los problemas encontrados, con su causa raíz;
- el análisis de refactorización;
- el plan de corrección.

Las mejoras aplicadas y su impacto medido van en `REPORT.md`, al final del ciclo.

Rama `feature/perf-audit`. Código analizado: el de `6877599` (merge de la PR #24), que es el que se midió.

| Documento de apoyo | Qué contiene |
|---|---|
| [`audit/before/runs.md`](audit/before/runs.md) | Registro completo de la medición: condiciones, cada ejecución y las comprobaciones de los 12 JSON |
| [`audit/skills-findings.md`](audit/skills-findings.md) | Ejecución de las skills `core-web-vitals` y `performance`: cada hallazgo con la sección de la skill que lo respalda |

---

## 1. Alcance y método

### Qué se midió

| Frontend | Qué es | Páginas | Por qué esas páginas |
|---|---|---|---|
| Sitio corporativo ([`uis/website`](uis/website/)) | HTML estático sin build, Tailwind CSS v4 por el Play CDN; en producción lo publica Netlify | `/` (index) y `/application.html` | El index es la home, la página de SEO y la más pesada (lleva la única foto). `application.html` es el formulario de registro de talento, la otra vista con contenido y la única con más JavaScript propio (`validations.js`) |
| Backoffice ([`uis/backoffice`](uis/backoffice/)) | Next.js 16.3.2 (App Router) | `/login`, `/incident-manager`, `/suppliers`, `/inventory/products` | `/login` es la puerta de entrada y la única carga sin caché ni sesión. Las otras tres son las vistas con tablas y datos reales: incident-manager (97 incidencias, resumen y filtros; la página más larga, 8504 px en mobile), suppliers (15 proveedores, con edición en fila) e inventory/products (el listado del inventario, con stock) |

En el backoffice no se midieron dos vistas:

- **`/`:** solo enlaza a las herramientas.
- **`/incidents`:** al cargar, es un formulario de subida vacío, y el resultado solo aparece tras subir un CSV. Lighthouse en modo *Navigation* mide la carga, no ese estado.

Cada página se midió en **mobile y desktop**: 12 casos en total.

### Cómo se midió

- **Herramienta:** el panel Lighthouse de Chrome DevTools, ejecutado a mano por el usuario. No se usaron ni el CLI de Lighthouse ni PageSpeed Insights.
- **Versiones:** Lighthouse 13.4.1 y Chrome 155. Modo *Navigation*, *throttling* simulado y las 4 categorías.
- **Ventana:** de incógnito, sin extensiones, una pestaña.
- **Mobile:** viewport de 412×823 emulado; RTT de 150 ms, 1,6 Mbps y CPU ×4.
- **Desktop:** 1526 px de ancho; RTT de 40 ms, 10 Mbps y CPU ×1.
- **Modo producción:**
  - **Backoffice:** `npm run build` y después `npm run start -- -p 3003`. Nunca `next dev`. Hablaba con la API real de Docker (TinyDB con 97 incidencias y 15 proveedores; el inventario en la base de demo de Supabase), siempre a través de su propio origen (`/backend`).
  - **Sitio:** no tiene build. Su equivalente local es un servidor estático: `node uis/serve-website.mjs`, el mismo del contenedor de desarrollo.
- **Condiciones de cada caso:**

  | Casos | «Clear storage» | Sesión | Calentamiento |
  |---|---|---|---|
  | Sitio (4) | marcado (en frío) | — | no |
  | `/login` (2) | marcado (en frío) | sin sesión | no |
  | Vistas con datos (6) | desmarcado | con sesión | una ejecución descartada por caso |

  Las vistas protegidas necesitan el token de `localStorage`; si se borrara, Lighthouse mediría la redirección a `/login`. Los 12 JSON confirman que la URL final es la pedida.
- **Repeticiones:** 3 o 4 ejecuciones por caso. La Performance no varió más de 1 punto en ningún caso.
- **Fuente de las cifras:** el JSON guardado de cada caso; la captura es la evidencia visual.
- **Commit medido:** `fb3cb15`, con el mismo código que `6877599`.

### Criterio de «corrección requerida»

El brief pide aplicar las correcciones que las skills clasifiquen como *requeridas*. Las skills no traen esa etiqueta, así que el usuario fijó el criterio. Una corrección es **requerida** si:

- **(a)** una métrica medida incumple su umbral: Performance < 90, LCP > 2,5 s, CLS > 0,1 o TBT > 200 ms (en *Navigation*, Lighthouse no mide INP; el TBT es su aproximación de laboratorio); o
- **(b)** una auditoría falla con un ahorro estimado y la skill la señala como causa.

Todo lo demás es **sugerencia**.

### Limitaciones

- **Sin datos de campo.** Todo es laboratorio: se mide en local y no hay CrUX ni RUM. Las mejoras que se midan después serán de laboratorio; ninguna se podrá presentar como mejora para usuarios reales sin datos de campo.
- **Servidor local.** La compresión, la caché, HTTP/2 y el TTFB (1–3 ms) son los del servidor de la medición, no los de producción. Se documentan y se descartan (§3.4).
- **Simulación.** FCP, LCP, TBT y Speed Index son estimaciones del modelo de Lighthouse. Cuando el modelo y la traza observada no coinciden, se dice (N2, en §3.3). El CLS no se simula: es el observado.
- **Sin traza de rendimiento.** No se grabó ninguna traza del panel Performance. Lighthouse 13 no informa de la causa de ningún desplazamiento (`cause`/`extra` vacíos). Las causas de CLS se deducen de la geometría del JSON y del código, y se confirman al volver a medir tras cada corrección.

---

## 2. Puntuaciones iniciales

Ejecución guardada de cada caso. FCP, LCP, TBT y CLS son los valores de Lighthouse. Las celdas en **negrita** incumplen el umbral.

| # | App | Página | Modo | Condición | Perf | A11y | BP | SEO | FCP | LCP | TBT | CLS | Captura |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | website | index | mobile | en frío | 98 | 100 | 100 | 100 | 1,9 s | 2,1 s | 10 ms | 0 | [png](audit/before/website/index/index-mobile.png) |
| 2 | website | index | desktop | en frío | 100 | 100 | 100 | 100 | 0,5 s | 0,5 s | 0 ms | 0 | [png](audit/before/website/index/index-desktop.png) |
| 3 | website | application | mobile | en frío | 98 | 100 | 100 | 100 | 1,9 s | 2,0 s | 30 ms | 0 | [png](audit/before/website/application/application-mobile.png) |
| 4 | website | application | desktop | en frío | 100 | 100 | 100 | 100 | 0,5 s | 0,5 s | 0 ms | 0 | [png](audit/before/website/application/application-desktop.png) |
| 9 | backoffice | login | mobile | en frío, sin sesión | 100 | 100 | 100 | 100 | 0,8 s | 1,7 s | 20 ms | 0 | [png](audit/before/backoffice/login/login-mobile.png) |
| 10 | backoffice | login | desktop | en frío, sin sesión | 100 | 100 | 100 | 100 | 0,2 s | 0,4 s | 0 ms | 0,003 | [png](audit/before/backoffice/login/login-desktop.png) |
| 5 | backoffice | incident-manager | desktop | con sesión | 100 | 100 | 100 | 100 | 0,2 s | 0,3 s | 0 ms | 0,032 | [png](audit/before/backoffice/incident-manager/incident-manager-desktop.png) |
| 6 | backoffice | incident-manager | mobile | con sesión | **82** | 100 | 100 | 100 | 0,6 s | 1,0 s | 20 ms | **0,373** | [png](audit/before/backoffice/incident-manager/incident-manager-mobile.png) |
| 7 | backoffice | suppliers | desktop | con sesión | 100 | 100 | 100 | 100 | 0,2 s | 0,2 s | 0 ms | 0,032 | [png](audit/before/backoffice/suppliers/suppliers-desktop.png) |
| 11 | backoffice | suppliers | mobile | con sesión | 95 | 100 | 100 | 100 | 0,6 s | 1,1 s | 80 ms | **0,136** | [png](audit/before/backoffice/suppliers/suppliers-mobile.png) |
| 8 | backoffice | inventory/products | desktop | con sesión | 100 | 100 | 100 | 100 | 0,2 s | 0,2 s | 0 ms | 0,032 | [png](audit/before/backoffice/inventory-products/inventory-products-desktop.png) |
| 12 | backoffice | inventory/products | mobile | con sesión | 95 | 100 | 100 | 100 | 0,6 s | 0,9 s | 60 ms | **0,135** | [png](audit/before/backoffice/inventory-products/inventory-products-mobile.png) |

El número de caso es el orden en que se planificó la medición. Los casos 9–12 se añadieron después, para medir el login en frío y las tres vistas con datos también en mobile.

**Lectura de la tabla:**

- **Accessibility, Best Practices y SEO están a 100 en los 12 casos.** Los problemas son todos de rendimiento.
- **El sitio no incumple ningún umbral.** Su peor dato es el LCP mobile de 2,1 s, cerca del límite de 2,5 s.
- **El backoffice falla en un solo indicador, el CLS,** y solo en mobile: las tres vistas con datos superan 0,1. En incident-manager el CLS de 0,373 hunde la Performance hasta 82, la única por debajo de 90.
- **TBT** (máximo 80 ms) y **LCP** (máximo 1,1 s con sesión) están bien en todo el backoffice.
- **TTFB:** de 1 a 3 ms en los 12 casos (§3.4).

---

## 3. Problemas identificados y causa raíz

Cuatro problemas tienen corrección requerida (§3.1). Los demás quedan como sugerencias (§3.2), se documentan sin corrección (§3.3) o se descartan por ser artefactos del entorno local (§3.4).

### 3.1 Requeridos

#### H1 — La cabecera del backoffice crece al validarse la sesión y empuja toda la página

**Síntoma medido:**

| Caso | Elemento que Lighthouse señala como desplazado | Puntuación |
|---|---|---|
| suppliers mobile | `body > main` | 0,1336942940441483 |
| inventory/products mobile | `body > main` | 0,1336942940441483 |
| incident-manager mobile | `body > main` (más otro desplazamiento, ver H2) | 0,1336942940441483 |
| incident-manager desktop | `body > main` | 0,032271 |
| suppliers desktop | `body > header > div` | 0,032270 |
| inventory/products desktop | `body > header > div` | 0,032270 |

Es el **único motivo** de que suppliers e inventory/products superen 0,1 en mobile. Además, supone más de un tercio del CLS de incident-manager.

**Causa raíz: la víctima es `main`; la causa, la cabecera.**

1. **Una cifra idéntica en tres vistas distintas.** El desplazamiento de `main` vale lo mismo, con 16 decimales, en tres vistas que no comparten contenido. Eso descarta que lo provoque algo de cada vista: tiene que estar en el layout común, en [`app/layout.tsx:20-33`](uis/backoffice/app/layout.tsx). Ahí solo hay dos piezas, la cabecera y `main`, y la cabecera va encima.
2. **La cabecera cambia de altura.** Según la geometría que guarda cada JSON (`fullPageScreenshot.nodes`), `main` acaba empezando en `top: 170` en mobile y en `top: 134` en desktop. En el login, que no tiene navegación con sesión, empieza en `top: 53`. Esos 53 px son exactamente la cabecera solo con la marca: `py-4` (32 px), una línea `text-sm` (20 px) y el borde (1 px).
3. **El código explica el cambio:**
   - [`components/auth/account-nav.tsx:24-55`](uis/backoffice/components/auth/account-nav.tsx): mientras la sesión está en `initializing` o `checking`, `AccountNav` devuelve `null` (línea 55). Con `authenticated`, pinta 8 elementos: 6 enlaces, el email y «Cerrar sesión».
   - [`hooks/use-auth-session.ts:68`](uis/backoffice/hooks/use-auth-session.ts), `:75` y `:188-191`: en el servidor y durante la hidratación, el token no se conoce (`initializing`). Con token, el estado es `checking` hasta que responde `GET /auth/me`.

   Así que el HTML del servidor y la primera pintura llevan la cabecera de 53 px. Cuando `/auth/me` confirma la sesión, aparece la navegación. No cabe en una línea, ni en 412 px ni en los 896 px de `max-w-4xl`, así que la cabecera crece y empuja hacia abajo todo `main`.
4. **La geometría reproduce la cifra medida.** Un desplazamiento puntúa *fracción de impacto × fracción de distancia*. En mobile (viewport de 412×823):
   - **Distancia:** `main` baja 117 px (de 53 a 170). 117 / 823 = 0,142.
   - **Impacto:** antes, `main` ocupaba de 53 a 823 en pantalla; después, de 170 a 823. La unión es de 53 a 823: 770 / 823 = 0,936.
   - **Resultado:** 0,936 × 0,142 ≈ **0,133**, la cifra medida.
5. **Desktop: el mismo evento, por debajo del umbral.** La cabecera pasa de 53 a 134 px. Lighthouse atribuye el desplazamiento a veces a `main` y a veces al contenedor de la cabecera, pero la puntuación es la misma (0,03227) en las tres vistas: es el mismo evento.

Es la cascada del guard de autenticación (§3.3, N1), vista desde la cabecera.

**Corrección prevista.** Reservar el espacio de la navegación mientras se comprueba la sesión, solo en las rutas protegidas:

- **Qué pinta:** en `initializing`/`checking`, `AccountNav` pinta la navegación con sesión, pero invisible y no interactiva (`invisible`, `aria-hidden`, `inert`) y con un marcador en lugar del email.
- **Sin enlaces reales:** cada entrada es un `<span>` con las mismas clases y el mismo texto, sin `Link` ni `href`. Así Next no precarga rutas protegidas durante la carga y el HTML sin sesión no contiene enlaces protegidos.
- **Desde el servidor:** la ruta y el estado `initializing` se conocen también en el servidor, así que el HTML inicial ya trae la cabecera con su altura final.
- **Sin duplicar marcado:** una única pieza interna decide, con una prop, entre enlace y `span`.
- **Lo que no cambia:** las rutas públicas (`/login`, `/register`…) quedan como hoy, y el guard no se toca (D10).

**Alternativas descartadas:**

- **Un `min-height` fijo en la cabecera:** frágil; la altura depende del ancho y del email.
- **Mostrar los enlaces antes de validar la sesión:** lo prohíbe AUTH-02.
- **Un menú plegable en mobile:** es rediseñar, no corregir.

**Impacto esperado (estimación):**

- desaparece el desplazamiento de `main`;
- suppliers e inventory/products bajan a CLS ≈ 0,003 y ≈ 0,001 en mobile;
- incident-manager mobile baja a ≈ 0,24, todavía por encima del umbral hasta H2;
- las tres vistas desktop bajan a ≈ 0.

**Riesgo:**

- **Medio-bajo, por tocar la cabecera de AUTH-02.** Se verifica con el recorrido de autenticación en el navegador y con la pestaña Network: ninguna precarga de rutas protegidas antes de que `/auth/me` responda.
- **Residuales sin medir:**
  - un token caducado o un error de red al validar cierran el hueco reservado;
  - un email mucho más largo que el marcador puede dejar un desplazamiento pequeño.

Detalle completo en [`skills-findings.md` §3 (H1)](audit/skills-findings.md).

#### H2 — El resumen de `/incident-manager` crece al llegar sus datos y empuja el listado

**Síntoma medido.** En incident-manager mobile hay un segundo desplazamiento: el de la sección del listado (`section[aria-labelledby="incident-list-heading"]`), que vale **0,2344**. Sumado a H1 (0,1337) y al de los filtros (0,0052), da el CLS de **0,373**, que deja la Performance en **82**. En desktop este desplazamiento no aparece.

**Causa raíz.** Encima del listado está el panel de resumen ([`components/incident-manager/incident-board-view.tsx:40-42`](uis/backoffice/components/incident-manager/incident-board-view.tsx)). Tiene su propia petición (`GET /api/incidents/summary`) y su propia carga ([`incident-summary-panel.tsx`](uis/backoffice/components/incident-manager/incident-summary-panel.tsx)):

- **mientras carga** (`:40-45`): ocupa una sola fila, «Cargando resumen…», de unos 60 px;
- **al llegar los datos** (`:47-56`): pinta una rejilla `grid-cols-1 sm:grid-cols-2 lg:grid-cols-4` con 4 listas (por estado, categoría, origen y sede). Tienen 4, 8, 3 y 4 filas: en mobile van apiladas, así que son 19 filas y 4 títulos;
- **además** (`:25`): aparece la línea «Total de incidencias».

Cuando llega la respuesta, el panel crece varios cientos de píxeles y empuja la sección del listado, que acaba en `top: 1048`, fuera de la pantalla. Antes de desplazarse estaba dentro del viewport.

En desktop, las 4 listas van en 4 columnas y la diferencia de altura es mucho menor. Sin traza no se puede distinguir si no se registró por eso o por el orden en que llegaron las dos respuestas. Es la **causa probable**, y se confirma al volver a medir.

**Corrección prevista.** Mientras el resumen no ha llegado, pintar la misma rejilla con las 4 listas y todas sus filas, con un marcador («—») en lugar de cada número y la línea del total reservada:

- las filas salen del vocabulario de [`types/incident-manager.ts:15-27`](uis/backoffice/types/incident-manager.ts);
- la altura final es exacta porque el contrato garantiza una entrada por valor ([`services/normalizers.ts:455-467`](uis/backoffice/services/normalizers.ts), `readCounts`);
- el panel mantiene su carga y su error aislados.

**Impacto esperado:**

- tras H1 y H2, el CLS de incident-manager mobile queda en el residual de los filtros (≈ 0,005);
- la Performance debería volver a ≥ 90, porque el CLS pesa un 25 % en la puntuación de Lighthouse 13.

**Riesgo:** bajo. Si el resumen falla en la primera carga, el aviso de error tiene otra altura y queda un desplazamiento en ese caso.

#### H3 — El Play CDN de Tailwind bloquea el primer pintado del sitio

**Síntoma medido** (`render-blocking-insight`, fallida en los 4 casos del sitio):

| Caso | Ahorro estimado si no bloqueara |
|---|---|
| index mobile | FCP y LCP: **1150 ms** |
| application mobile | FCP y LCP: **1100 ms** |
| index desktop | FCP: 300 ms |
| application desktop | FCP y LCP: 300 ms |

**Auditorías relacionadas, por el mismo script:**

- `unused-javascript`: 21 KiB sin usar de 56 KiB;
- `cache-insight`: 7 días de caché, servido por el CDN;
- `network-dependency-tree-insight`: la cadena documento → `cdn.jsdelivr.net`.

Los LCP mobile del sitio (2,1 y 2,0 s) son los más altos de toda la medición.

**Causa raíz.** Las 3 páginas cargan `<script src="https://cdn.jsdelivr.net/npm/@tailwindcss/browser@4">` en el `<head>`, sin `defer`:

- [`index.html:18`](uis/website/index.html);
- [`application.html:12`](uis/website/application.html);
- [`404.html:12`](uis/website/404.html).

El Play CDN no es una hoja de estilos: es JavaScript que **genera el CSS en el navegador**. Antes de pintar nada, el navegador tiene que:

1. abrir una conexión con otro origen;
2. descargar 57 KB;
3. ejecutarlos;
4. recorrer el DOM buscando clases;
5. inyectar el CSS resultante.

No se le puede poner `defer`: la página se pintaría primero sin estilos y luego saltaría (FOUC, y CLS). Con el *throttling* de mobile, esa cadena es más de la mitad del LCP estimado.

Hay además un problema de mantenimiento: `@4` no fija la versión, que en la medición resolvió a la 4.3.3.

**Corrección prevista (D3, aprobada antes de medir):**

- **El CSS:** precompilar Tailwind con su CLI en una versión fija (`npx @tailwindcss/cli@4.3.3`), a un CSS minificado local que se enlaza con `<link rel="stylesheet">`.
- **Qué escanea el CLI:** también `src/js/*.js`, porque el JavaScript añade clases (`hidden`, `border-red-700`, el aviso del formulario).
- **Sin dependencias:** sin `package.json` ni dependencias nuevas.
- **Versionado:** el CSS generado se versiona, porque Netlify publica el sitio tal cual, sin build.
- **Documentación:** el comando va en un `uis/website/README.md` nuevo. La regla del monorepo pide un README por app, el sitio no lo tenía, y el paso de generación solo concierne a esta app. `uis/README.md` sigue como índice y se corrige su descripción («no build step»).

**Impacto esperado:**

- desaparece el bloqueo del JavaScript de terceros: FCP y LCP mobile por debajo de los 1,9 / 2,1 s actuales;
- desaparecen `unused-javascript` y la entrada del CDN en `cache-insight`;
- el CSS local seguirá bloqueando, como todo CSS, pero es del mismo origen, más pequeño y no ejecuta nada.

**Riesgo:**

- **Visual, medio:** una clase que el CLI no detecte desaparece. Se compara antes y después en desktop y a 375 px, con el menú móvil abierto y los estados de error y éxito del formulario.
- **Mantenimiento:** una clase nueva obliga a regenerar el CSS.

#### H4 — La foto del index se sirve a 1920×1156 para mostrarse a 576×347

**Síntoma medido.** `image-delivery-insight` falla en el index:

- desktop: la foto se muestra a 576×347, con **274 KiB** de ahorro estimado;
- mobile: se muestra a 380×229, con **295 KiB**.

La foto (308 KB) es unas cuatro quintas partes de los 377 KiB que pesa el index (`total-byte-weight`). No tiene ahorro en ninguna métrica.

**Causa raíz.** [`index.html:219-224`](uis/website/index.html) sirve el original de cámara ([`src/img/ambiente-trabajo-nexova.jpg`](uis/website/src/img/ambiente-trabajo-nexova.jpg)), en JPEG y sin `srcset`, a cualquier pantalla.

Tiene bien `width`/`height` (no causa CLS) y `loading="lazy"`. Está debajo del pliegue y no es el LCP de ningún modo, así que pesa en los bytes, no en las métricas.

**Corrección prevista (D4):**

- generar 768 y 1152 px de ancho en WebP, con un JPEG recomprimido de respaldo, con `npx sharp-cli@<versión fija>` puntual y sin dependencias;
- servirlas con `<picture>`, `srcset` y `sizes`;
- conservar `width`/`height`, `loading="lazy"` y el `alt`.

**Impacto esperado:** solo en bytes: `image-delivery-insight` sin ahorro pendiente y el peso del index muy por debajo de 377 KiB. **No se espera cambio en la puntuación ni en el LCP**, y `REPORT.md` lo dirá así.

**Por qué es requerida.** Es requerida por el criterio (b): la auditoría falla con ahorro estimado y la sección *Image optimization* de la skill `performance` prescribe exactamente esta corrección. Es la última de las cuatro porque no mueve ningún KPI.

### 3.2 Sugerencias (no se corrigen, salvo S1)

| ID | Qué | Evidencia | Por qué no es requerida / decisión |
|---|---|---|---|
| S1 | `logo.svg` sin `width`/`height` en los 3 HTML (`index.html:70`, `application.html:28`, `404.html:35`). En el index desktop es el LCP y no tiene `fetchpriority="high"` | `unsized-images` y `lcp-discovery-insight` fallan, pero sin ahorro estimado (el CLS del sitio es 0) | No tiene ahorro, pero es barata y es una causa habitual que cita el brief. **Se aplicará después de H3, en su propio commit, si sigue teniendo sentido:** al quitar el script del CDN puede cambiar cuál es el LCP del index desktop |
| S2 | CSS bloqueante de Next en el login en frío (`3041c5xfhjw05.css`, 4,8 KB) | `render-blocking-insight`: 150 ms en el login mobile. Con sesión, el CSS sale de la caché y no hay ahorro | La skill (`LCP.md`) pide además un *render delay* largo, y hay 71 ms. El LCP del login (1,7 s) cumple. La solución (`experimental.inlineCss`) es experimental y global, y empeora las visitas recurrentes, que es el uso diario del backoffice |
| S3 | Polyfills (`Array.prototype.at`, `flat`, `Object.hasOwn`…) y JavaScript sin usar del chunk `0zutzion2550z.js` | `legacy-javascript-insight` (13–14 KiB) y `unused-javascript` (26 KiB, solo en el login), con ahorro FCP/LCP de 0 | No es código de la app: el chunk empieza con el `polyfill-module` del propio Next.js, y la app ya usa los navegadores modernos por defecto de Next 16. Quitarlo exigiría intervenir el build del framework |
| S4 | `src/js/validations.js` sin minificar | `unminified-javascript`: 4 KiB, sin ahorro en métricas | Netlify lo sirve comprimido en producción, y minificarlo añadiría otro archivo generado que mantener |
| S5 | Desplazamientos residuales: filtros de incident-manager (0,0052) y de suppliers (0,0026), leyenda del stock del inventario (0,0014), navegación sin sesión en el login desktop (0,003) | `layout-shifts` | Muy por debajo de 0,1 en todos los casos, una vez corregidos H1 y H2 |

### 3.3 Documentados, sin corrección

**N1 — La espera del guard retrasa el pintado del contenido (D10).**

- **Síntoma:** en las vistas con sesión, el LCP es un párrafo de la página, con un *render delay* de 166–206 ms en mobile (`lcp-breakdown-insight`).
- **Causa:** el guard global ([`components/auth/auth-guard.tsx:30`](uis/backoffice/components/auth/auth-guard.tsx) y `:53-58`) no pinta la vista hasta que `GET /auth/me` confirma la sesión. Hasta entonces, `main` solo muestra «Comprobando la sesión…», aunque el título y el párrafo vengan de Server Components. El token está en `localStorage`, que el servidor no puede leer.
- **Por qué no se corrige:** cambiarlo exigiría cookies o middleware, que la arquitectura de autenticación del backoffice prohíbe. Además, todos los LCP cumplen con holgura (el máximo es 1,1 s). Decisión D10: se documenta como causa y no se corrige. H1 corrige su efecto en el CLS sin tocar la cascada.

**N2 — El hueco de 900 ms entre FCP y LCP del login mobile es un artefacto de la simulación.**

- **Síntoma:** el modelo de Lighthouse estima un FCP de 757 ms y un LCP de 1657 ms. Pero en la carga observada, sin *throttling*, FCP y LCP caen en el mismo instante: 78 ms.
- **Indicios:**
  - el LCP simulado cambió entre ejecuciones (2,2 / 2,1 / 1,7 / 1,7 s) con el FCP fijo;
  - el elemento LCP es un párrafo que ya viene en el HTML del servidor (`/login` es una ruta pública y se pinta en cualquier estado de la sesión).
- **Causa probable:** el modelo incluye en el LCP los chunks JavaScript de Next, que la página real no espera para pintar ese párrafo.
- **Conclusión:** nada que corregir. El LCP cumple en todas las ejecuciones.

### 3.4 Descartados: artefactos del servidor local

Las dos skills recomiendan compresión, HTTP/2, caché de los estáticos y un TTFB < 800 ms. Aquí lo que se observa es el servidor de la medición, no el de producción:

| ID | Qué | Evidencia | Por qué se descarta |
|---|---|---|---|
| X1 | Sin compresión | `document-latency-insight`: «No compression applied» en el HTML del sitio (10–14 KiB), sin ahorro en métricas | `serve-website.mjs` no comprime; en producción el sitio lo sirve Netlify |
| X2 | Sin caché | Los archivos locales se envían con `Cache-Control: no-store` y quedan fuera de `cache-insight` | Política del servidor local. La única entrada de `cache-insight`, el script del CDN, desaparece con H3 |
| X3 | HTTP/1.1 | `modern-http-insight` pasa porque es localhost, pero el servidor solo habla HTTP/1.1 | El protocolo lo da la plataforma de despliegue |
| X4 | TTFB | 1–3 ms (`server-response-time`) en los 12 casos | Localhost: muy por debajo de 800 ms y nada representativo de producción |

---

## 4. Análisis de refactorización

El brief pide identificar al menos dos casos de componentes o lógica repetidos que puedan extraerse en un componente compartido o un Custom Hook.

Los tres casos de esta sección se han verificado en el código actual: archivos, líneas y cuánto se repite. Los dos primeros (R1 y R2) son los aprobados en F0 para implementar. R3 sigue siendo válido, pero queda como candidato sin aplicar. Los tres son del backoffice; el caso del sitio se descarta (R4).

### R1 — `components/ui/table-scroll.tsx`: el contenedor de las tablas con scroll horizontal

**Dónde aparece.** Las cuatro tablas de datos repiten el mismo armazón: contenedor con scroll, `<table>`, `<caption>` accesible y cabecera con el mismo estilo.

| Archivo | Contenedor | `<table>` | Ancho mínimo |
|---|---|---|---|
| [`components/incident-manager/incident-table.tsx:33-36`](uis/backoffice/components/incident-manager/incident-table.tsx) | `relative overflow-x-auto rounded-lg border border-border bg-surface` | `w-full min-w-[48rem] border-collapse text-left text-sm` | 48rem |
| [`components/suppliers/supplier-table.tsx:25-28`](uis/backoffice/components/suppliers/supplier-table.tsx) | `overflow-x-auto rounded-lg border border-border bg-surface` (**sin `relative`**) | `w-full min-w-[46rem] …` (igual) | 46rem |
| [`components/inventory/asset-table.tsx:21-24`](uis/backoffice/components/inventory/asset-table.tsx) | `relative overflow-x-auto …` (igual) | `w-full min-w-[44rem] …` (igual) | 44rem |
| [`components/inventory/order-table.tsx:17-20`](uis/backoffice/components/inventory/order-table.tsx) | `relative overflow-x-auto …` (igual) | `w-full min-w-[56rem] …` (igual) | 56rem |

**Cuánto se repite:**

- la cabecera (`border-b border-border bg-canvas text-xs uppercase tracking-wide text-ink-muted`) y el `<caption className="sr-only">`, en las 4;
- la clase de celda de cabecera `px-3 py-2 font-semibold`, **25 veces**;
- el comentario que explica el `relative` está copiado en `incident-table.tsx:29-32`, `asset-table.tsx:20` y `order-table.tsx:16`.

**Por qué es candidato.** La repetición ya ha producido un defecto. El `relative` evita que los elementos `sr-only` (con `position: absolute`) de dentro de la tabla ensanchen la página. Se añadió a mano en tres tablas tras el bug de scroll horizontal a 375 px de `/incident-manager`, pero **falta en `supplier-table.tsx`**, que también tiene un `sr-only` dentro (la etiqueta de la tarifa, `:167`).

El test estático que exige `relative` en todo `overflow-x-auto` mantiene una lista de excepciones pendientes, con `supplier-table.tsx` y las 3 tablas de `/incidents`:

- [`tests/production-source.test.mjs:407-418`](uis/backoffice/tests/production-source.test.mjs);
- `uis/backoffice/CLAUDE.md`, «Contenedores con scroll horizontal».

Con un componente, la regla vive en un solo sitio y la lista de excepciones de las tablas de datos desaparece.

**Cómo quedaría:**

```tsx
// components/ui/table-scroll.tsx
export interface TableScrollProps {
  /** Texto del <caption> (solo para lectores de pantalla). */
  caption: string;
  /** Ancho mínimo de la tabla antes de hacer scroll, como clase de Tailwind. */
  minWidthClass: 'min-w-[44rem]' | 'min-w-[46rem]' | 'min-w-[48rem]' | 'min-w-[56rem]';
  /** Cabeceras de columna, en orden. */
  columns: readonly string[];
  /** Las filas (<tr>) del <tbody>. */
  children: ReactNode;
}

export function TableScroll({ caption, minWidthClass, columns, children }: TableScrollProps): JSX.Element;
```

- **Qué pinta:** el contenedor `relative overflow-x-auto …`, la `<table>`, el `<caption>`, el `<thead>` con un `<th scope="col">` por columna y el `<tbody>` con `children`.
- **El ancho mínimo:** va como unión de clases literales porque Tailwind solo genera las clases que encuentra escritas en el código.
- **Quién lo usaría:** las 4 tablas. Cada una conserva sus filas, que son distintas: selector de estado, edición de tarifa, enlaces de entrada y salida, insignias.
- **Las 3 tablas de `/incidents`** (`distribution-table.tsx:22`, `invalid-breakdown-table.tsx:20`, `satisfaction-panel.tsx:36`) tienen otro estilo, sin borde ni cabecera común. Se dejan fuera de R1 para no cambiar su aspecto. Siguen en la lista de excepciones del test.

**Riesgo.** Bajo, sin cambio visual en las 4 tablas, salvo el `relative` que gana la de proveedores. Tests que habrá que ajustar:

- el de `production-source.test.mjs:354`, que busca el literal `className="relative overflow-x-auto` en `order-table.tsx`: pasará a comprobarlo en `table-scroll.tsx` y a exigir que la tabla lo use;
- la lista de excepciones (`:413-418`): sale `supplier-table.tsx`.

### R2 — Un hook genérico de carga de listados para el inventario

**Dónde aparece:**

- [`hooks/use-inventory-assets.ts`](uis/backoffice/hooks/use-inventory-assets.ts): los activos, que usan 6 componentes (`asset-list-view`, `asset-select`, `inbound-form-view`, `inbound-form`, `outbound-form-view`, `outbound-form`);
- [`hooks/use-inventory-orders.ts`](uis/backoffice/hooks/use-inventory-orders.ts): el historial, que usa `order-history-view`.

**Cuánto se repite:**

- **159 líneas cada archivo.** Un `diff` entre los dos solo muestra nombres: `Asset`/`InventoryOrder`, `assets`/`orders`, `listAssets`/`listOrders` y los nombres de los tipos y funciones.
- **Las tres piezas son idénticas:**
  1. el reducer puro, con `load_started`/`load_succeeded`/`load_failed`, y la vista derivada `'loading' | 'error' | 'empty' | 'data'`;
  2. la sesión sin React, con activación compatible con StrictMode, cancelación con `AbortController`, el contador `run` contra carreras y el error de reserva;
  3. el hook, con `useReducer` + `useState` + `useEffect` + `useCallback`.

**Por qué es candidato.** Es lógica no trivial: carreras, cancelación al desmontar, conservar el último listado tras un fallo. Un arreglo en una copia no llega a la otra, y una tercera vista del inventario la copiaría de nuevo. Además, las dos suites (`tests/use-inventory.test.mjs` y `tests/use-inventory-orders.test.mjs`, 189 y 149 líneas) prueban cada una su propia copia de la misma sesión.

**Cómo quedaría:**

```ts
// hooks/use-inventory-list.ts
export interface InventoryListState<T> {
  items: readonly T[];
  loaded: boolean;
  load: { status: 'idle' } | { status: 'loading' } | { status: 'success' } | { status: 'error'; error: InventoryUiError };
}
export type InventoryListView = 'loading' | 'error' | 'empty' | 'data';

export function inventoryListReducer<T>(state: InventoryListState<T>, action: InventoryListAction<T>): InventoryListState<T>;
export function inventoryListView<T>(state: InventoryListState<T>): InventoryListView;
export function createInventoryListSession<T>(
  dispatch: (action: InventoryListAction<T>) => void,
  fetchList: (options: { signal: AbortSignal }) => Promise<readonly T[]>
): InventoryListSession;
export function useInventoryList<T>(fetchList: (options: { signal: AbortSignal }) => Promise<readonly T[]>): UseInventoryListResult<T>;
```

`use-inventory-assets.ts` y `use-inventory-orders.ts` quedan como envoltorios finos, de pocas líneas, que conservan su API pública actual:

```ts
export function useInventoryAssets(): UseInventoryAssetsResult {
  const { items, ...rest } = useInventoryList(listAssets);
  return { ...rest, assets: items };
}
```

Las mismas `assets`/`orders`, `view`, `loaded`, `load` y `reload` que hoy. Así los 7 componentes no cambian.

- **`fetchList`:** tiene que ser una referencia estable: la función del servicio, no una flecha creada en cada render.
- **Tests:** las pruebas de carreras y cancelación pasan al genérico, una sola vez.

**Riesgo.** Bajo, porque la API pública se conserva. Se verifica con la suite de `uis/backoffice` y con el recorrido del inventario en el navegador:

- Activos;
- el selector de Entrada y Salida;
- el Historial;
- la API parada, con «Reintentar».

### R3 — Bloque de «Cargando…» de los listados (candidato, no se aplica)

**Dónde aparece.** El mismo bloque de carga está copiado literalmente en 4 vistas:

```tsx
<div className="flex items-center gap-3 rounded-lg border border-dashed border-border bg-surface p-6">
  <LoadingSpinner />
  <span className="text-sm text-ink-muted">Cargando …</span>
</div>
```

- [`components/incident-manager/incident-board-view.tsx:70-73`](uis/backoffice/components/incident-manager/incident-board-view.tsx);
- [`components/inventory/asset-list-view.tsx:57-60`](uis/backoffice/components/inventory/asset-list-view.tsx);
- [`components/inventory/order-history-view.tsx:49-52`](uis/backoffice/components/inventory/order-history-view.tsx);
- [`components/suppliers/supplier-directory-view.tsx:110-113`](uis/backoffice/components/suppliers/supplier-directory-view.tsx).

El estado vacío repite el mismo marco discontinuo (`rounded-lg border border-dashed border-border bg-surface p-6`) en esas 4 vistas, pero con contenido distinto en cada una (dos párrafos, un enlace, un texto según los filtros).

**Cómo quedaría:** `components/ui/list-placeholder.tsx`, con:

- `ListLoading({ label }: { label: string })`, para el bloque de carga;
- `ListEmpty({ children }: { children: ReactNode })`, para el marco del estado vacío.

**Por qué no se aplica.** Son 4 líneas de marcado sin lógica, y el brief pide al menos un caso extraído (R1 y R2 ya lo cubren). Además, este bloque está en las vistas que tocan H1 y H2: hacerlo a la vez mezclaría efectos en las mediciones. Queda como candidato documentado.

### R4 (descartado) — Cabecera y pie copiados en los 3 HTML del sitio

**Dónde aparece:**

| Página | Cabecera | Pie |
|---|---|---|
| [`uis/website/index.html`](uis/website/index.html) | líneas 65–151 | líneas 284–308 |
| [`uis/website/application.html`](uis/website/application.html) | líneas 23–109 | líneas 314–338 |
| [`uis/website/404.html`](uis/website/404.html) | líneas 30–116 | líneas 142–166 |

En total, 87 líneas de cabecera (con el menú móvil) y 25 de pie por página. Las copias solo difieren en los `href` (`#inicio` frente a `index.html#inicio`) y en qué enlace lleva `aria-current="page"`.

**Por qué se descarta.** El sitio es HTML estático sin build, y Netlify lo publica tal cual. Para compartir la cabecera habría dos caminos, y ninguno vale:

- **Inyectarla con JavaScript:** la navegación no estaría en el HTML inicial. Se perdería para los buscadores y para quien no ejecute JavaScript, y la cabecera aparecería tarde: un desplazamiento que hoy no existe (el CLS del sitio es 0). Es empeorar el SEO y el rendimiento, justo lo que la auditoría intenta mejorar.
- **Una plantilla con build:** cambia la arquitectura del sitio para resolver un problema de mantenimiento, no de rendimiento, y el brief lo prohíbe («No reestructures la arquitectura»).

La duplicación se documenta como deuda; no se corrige en esta auditoría.

---

## 5. Plan de corrección

Orden aprobado. Primero lo que incumple umbral, en el backoffice: es el CLS, y es lo que afecta de verdad a quien usa la herramienta a diario en el móvil. Después, lo que solo es requerido por el criterio de la skill, en el sitio. Por último, las refactorizaciones y la medición final.

Un problema por commit. Tras cada paso, el usuario vuelve a ejecutar Lighthouse en las mismas condiciones de §1:

- **Ejecuciones:** **1 por caso**, solo en los casos afectados.
- **Qué se guarda:** solo el JSON, en `audit/after/steps/<paso>/<página>-<modo>.json`, sin capturas. El CLS es determinista y la Performance varió ≤ 1 punto entre ejecuciones en la medición inicial.

| Paso | Qué | Se vuelve a medir (URL · modo) | Qué se espera |
|---|---|---|---|
| 1 | **H1**: reservar el espacio de la navegación mientras se valida la sesión | `/suppliers`, `/inventory/products` e `/incident-manager` · mobile y desktop; `/login` · mobile y desktop como control | Sin el desplazamiento de `main`: suppliers e inventory mobile con CLS < 0,1; incident-manager mobile aún por encima; login sin cambios. Además, en Network, ninguna precarga de rutas protegidas antes de `/auth/me` |
| 2 | **H2**: reservar el espacio del resumen de incidencias | `/incident-manager` · mobile y desktop | CLS < 0,1 y Performance ≥ 90 en mobile |
| 3 | **H3**: Tailwind precompilado (D3) | `/` y `/application.html` · mobile y desktop, más la comparación visual en desktop y a 375 px | Sin el script del CDN en `render-blocking-insight`; FCP/LCP mobile más bajos; CLS 0 |
| 4 | **H4**: foto en tamaños adaptados y WebP (D4) | `/` · mobile y desktop | `image-delivery-insight` sin ahorro pendiente y menos peso total; puntuación sin cambio esperado |
| 5 | **S1**: dimensiones del logo y `fetchpriority`, si tras H3 sigue teniendo sentido | `/` y `/application.html` · mobile y desktop | `unsized-images` y `lcp-discovery-insight` pasan |
| 6 | **R1**: `components/ui/table-scroll.tsx` | `/incident-manager`, `/suppliers` e `/inventory/products` · mobile | Ninguna regresión; las tablas, igual a la vista |
| 7 | **R2**: hook genérico de listados del inventario | `/inventory/products` · mobile y desktop | Ninguna regresión |
| 8 | **Medición final** | Los 12 casos, con 3 ejecuciones, capturas y JSON en `audit/after/<app>/<página>/`, igual que `audit/before/` | Base de la comparativa de `REPORT.md` |

URLs completas: el sitio en `http://localhost:3000` y el backoffice en `http://localhost:3003` (`npm run build` + `npm run start -- -p 3003`).

Las sugerencias S2–S5 no se aplican, y N1–N2 y X1–X4 quedan documentados.

Cada corrección de código se valida, además, con la validación de su subproyecto (`AGENTS.md` §4):

- **backoffice:** `tsc`, `lint`, `build`, `node:test` y Jest, más el recorrido manual de la vista afectada;
- **sitio:** verificación visual.

# Lighthouse — mediciones tras las correcciones

Registro de las mediciones posteriores a cada corrección de la auditoría de rendimiento. El plan está en [`AUDIT.md` §5](../../AUDIT.md) y la medición inicial en [`audit/before/runs.md`](../before/runs.md).

**Fuente de las cifras:** el JSON de cada caso. Las mediciones intermedias no llevan captura; la medición final sí.

## 1. Guía de medición

Son las mismas condiciones de la medición inicial ([`audit/before/runs.md` §1](../before/runs.md)), con dos reglas añadidas, aprendidas en H1. Ver §2 para el detalle de por qué.

**Plan final (decisión del usuario, 2026-10-28).**

- Mediciones intermedias solo tras H1 y H2 (§2).
- H3, H4 y R1 se aplicaron seguidos, sin medición intermedia.
- Una sola medición final con 1 ejecución por caso (§3). La justificación: en el antes, la Performance varió ≤ 1 punto entre ejecuciones y el CLS fue idéntico.
- El impacto de H3 y H4 se atribuye por sus auditorías en el JSON final (`render-blocking-insight`, `image-delivery-insight`, `total-byte-weight`). El de H1 y H2, por sus mediciones intermedias.

### Herramienta y navegador

- Panel Lighthouse de Chrome DevTools, ejecutado por el usuario. Nunca el CLI de Lighthouse ni PageSpeed.
- Modo *Navigation*, *throttling* simulado y las 4 categorías.
- **Ventana sin extensiones.** Una extensión permitida en incógnito también se inyecta en la página y entra en la medición. Desde H2 se mide en una ventana de invitado de Chrome, que no carga extensiones. Se comprueba en el JSON: ninguna petición `chrome-extension://` en `network-requests`.
- **El mismo ancho de ventana que en el antes.** En desktop no hay emulación de pantalla: el viewport es la ventana. El antes se midió a 1526 px; la medición final desktop, a 870 px (ver §3). Para comparar desktop con desktop, la ventana tiene que tener el mismo ancho. Se comprueba en el JSON con `fullPageScreenshot.screenshot.width`.

### Backoffice (`uis/backoffice`), en el 3003

1. Parar el contenedor `ui` (`docker compose stop ui`). La API (`api`) sigue en Docker.
2. **Siempre desde PowerShell**, nunca desde Git Bash. Git Bash (MSYS) convierte los valores que parecen rutas: `NEXT_PUBLIC_API_URL=/backend` acaba horneado en el bundle como `C:/Program Files/Git/backend` y todas las peticiones a la API fallan. Las variables, solo en esa sesión de PowerShell:

   ```powershell
   $env:API_INTERNAL_URL = 'http://localhost:8000'
   $env:NEXT_PUBLIC_API_URL = '/backend'
   $env:NEXT_PUBLIC_INVENTORY_API_URL = '/backend'
   npm run build
   npm run start -- -p 3003
   ```

3. **Comprobaciones antes de medir:**
   - `curl.exe localhost:3003/backend/health` → `{"status":"ok"}`;
   - ningún chunk de `.next/static/chunks/` contiene `Program Files`.
4. **Al terminar:**
   - parar el 3003;
   - volver a ejecutar `npm run build` sin las variables, para que los rewrites del `routes-manifest` queden vacíos;
   - `docker compose start ui`.

### Sitio (`uis/website`), en el 3000

- `node uis/serve-website.mjs`, con el contenedor `ui` parado.

### Condiciones por caso

| Casos | «Clear storage» | Sesión | Calentamiento |
|---|---|---|---|
| Sitio y `/login` | marcado (en frío) | sin sesión | no |
| Vistas con datos | desmarcado | con sesión | 1 ejecución descartada |

**Cuenta de prueba.** La cuenta que creó el agente en la TinyDB de desarrollo para verificar H1 y H2 en el navegador sigue en la base. Se borra al cerrar el ticket, con la confirmación del usuario. La sesión con la que el usuario mide no consta en los JSON.

### Qué se guarda

- **Tras H1 y H2:** 1 sola ejecución en la URL clave del paso. Solo el JSON, en `audit/after/steps/<paso>/<página>-<modo>.json`, sin capturas.
- **Medición final:** los 12 casos, con **1 ejecución** por caso. Captura y JSON en `audit/after/<app>/<página>/<página>-<modo>.{png,json}`, con la misma estructura que `audit/before/`.

**Comprobaciones de cada JSON:**

- `finalDisplayedUrl` es la URL pedida;
- `formFactor` es el esperado;
- Lighthouse 13.4.1;
- `runWarnings` está vacío;
- no hay peticiones `chrome-extension://`.

## 2. Mediciones intermedias

### H1 — espacio reservado de la navegación (`4e23d91`)

El build medido es el de `4e23d91`, compilado desde PowerShell. Según el plan revisado, 1 ejecución en cada una de las 2 URL clave.

**Comprobaciones:**

| Archivo | `finalDisplayedUrl` | `formFactor` | LH | `fetchTime` (UTC → local) | `benchmarkIndex` | `disableStorageReset` | `runWarnings` |
|---|---|---|---|---|---|---|---|
| `steps/H1/suppliers-mobile.json` | `http://localhost:3003/suppliers` | mobile | 13.4.1 | 2026-10-27 22:58:18Z → 23:58:18 | 3764 | `true` (con sesión) | vacío |
| `steps/H1/incident-manager-mobile.json` | `http://localhost:3003/incident-manager` | mobile | 13.4.1 | 2026-10-27 22:59:51Z → 23:59:51 | 3672,5 | `true` (con sesión) | vacío |

Las dos URL son las pedidas, sin redirección a `/login`. **Pero las dos ejecuciones tienen extensiones de Chrome activas** (ver «FCP», más abajo), y la medición inicial no tenía ninguna.

**Resultados frente al antes:**

| Caso | | Perf | FCP | LCP | TBT | CLS | SI |
|---|---|---|---|---|---|---|---|
| suppliers mobile | antes | 95 | 0,6 s (614 ms) | 1,1 s (1115 ms) | 78 ms | 0,136 | 0,6 s |
| | **H1** | **100** | 0,9 s (912 ms) | 1,1 s (1119 ms) | 61 ms | **0,003** | 0,9 s |
| incident-manager mobile | antes | 82 | 0,6 s (613 ms) | 1,0 s (958 ms) | 24 ms | 0,373 | 0,6 s |
| | **H1** | **88** | 0,9 s (922 ms) | 1,1 s (1132 ms) | 9 ms | **0,240** | 0,9 s |

Accessibility, Best Practices y SEO: 100 en los dos casos, como antes.

**`layout-shifts` frente al antes:**

| Caso | Antes | Tras H1 |
|---|---|---|
| suppliers mobile | `main.mx-auto` 0,1337 + filtros del directorio 0,0026 | filtros del directorio **0,0026** |
| incident-manager mobile | sección del listado 0,2344 + `main.mx-auto` 0,1337 + filtros 0,0052 | sección del listado 0,2344 + filtros 0,0052 |

**Conclusión sobre el CLS: H1 hace lo esperado.**

- **El desplazamiento de `main` desaparece** en los dos casos, y los demás siguen intactos, con las mismas puntuaciones.
- **Suppliers mobile** baja de 0,136 a 0,003 y queda en el umbral bueno.
- **Incident-manager mobile** baja de 0,373 a 0,240. Sigue por encima de 0,1 por el desplazamiento del listado, que es H2.
- **Las extensiones no alteran esta lectura:** los nodos desplazados son los de la app y sus puntuaciones no cambian.

**FCP: la subida de 0,6 a 0,9 s se debe a las condiciones de la medición, no a H1.**

El FCP sube en los dos casos: 614 → 912 ms y 613 → 922 ms. Los JSON lo explican.

| Dato | suppliers: antes → H1 | incident-manager: antes → H1 |
|---|---|---|
| Peticiones `chrome-extension://` | 0 → **5** | 0 → **5** |
| Extensiones en el informe | ninguna → 3 (`eppiocem…`, `gighmmpi…`, `npclhjbd…`) | ídem |
| Bytes transferidos en total | 22 175 → 42 782 (+20 607) | 25 110 → 45 729 (+20 619) |
| Bytes de los 5 scripts de la extensión | — → 20 624 | — → 20 624 |
| Peticiones en caché (`transferSize` 0) | 15 → 15 | 15 → 15 |
| CSS (bloqueante, desde caché) | 17 762 B, 0 transferidos → 17 829 B, 0 transferidos | ídem |
| HTML del documento (`resourceSize`) | 9218 → 11 012 B (+1794) | 9140 → 10 934 B (+1794) |
| HTML transferido (`transferSize`) | 373 → 373 B | 373 → 373 B |
| FCP observado (sin *throttling*) | 93 → **188 ms** | 60 → **178 ms** |
| `bootup-time` (CPU de scripts) | 339 → 634 ms | 341 → 676 ms |
| Trabajo del hilo principal | 985 → 1232 ms | 772 → 1254 ms |

**Lectura de la tabla:**

1. **Hay tres extensiones de Chrome activas en las dos ejecuciones de H1.** La que más pesa, `eppiocem…`, inyecta 5 scripts (`libs/extend-native-history-api.js`, `libs/requests.js`, `content/location/location.js`, `executors/200.js`, `executors/101.js`). Se piden entre los 61 y los 147 ms, antes del FCP observado. Además, su `ad-blocker/content.js` ocupa 111–121 ms de CPU en `bootup-time`.
2. **En la medición inicial no había ninguna** (0 peticiones `chrome-extension://` en los 12 JSON de `audit/before/`). Es la condición «incógnito, sin extensiones» de `audit/before/runs.md` §1, que esta vez no se cumplió.
3. **Lo demás es igual:** la misma caché (15 peticiones servidas desde caché, el CSS con 0 bytes transferidos), el mismo TTFB (2 ms) y el mismo *throttling*. La diferencia de bytes transferidos es exactamente la de los scripts de la extensión.
4. **La parte de H1 es despreciable.** H1 añade 1794 B al HTML: el marcado de la navegación reservada y su reflejo en el *payload* RSC. Pero el tamaño transferido del documento que registra Lighthouse es el mismo (373 B en los dos), así que esa diferencia no entra en el modelo de red de la simulación.
5. **El FCP observado se duplica** (de 93 a 188 ms y de 60 a 178 ms). La simulación multiplica ese trabajo de CPU previo al FCP (CPU ×4) y lo convierte en unos +300 ms de FCP simulado. El *render delay* del LCP sube por lo mismo (206 → 259 ms y 166 → 234 ms).

**Efecto en las puntuaciones:**

- **El CLS no se ve afectado.**
- **La Performance sí, en parte:** el FCP y el Speed Index pesan un 10 % cada uno. Es probable que la Performance real de H1 esté algo por encima de lo medido (100 y 88), pero no se adelanta cifra.
- **Para la comparación del FCP**, estas dos ejecuciones no valen: haría falta repetirlas sin extensiones. Lo decide el usuario.

**Verificación funcional de H1.** La hizo el agente antes de esta medición, con el mismo build; detalle en `memory-bank/progress.md`:

- el HTML del servidor ya trae la navegación reservada;
- ninguna precarga de rutas protegidas antes de `/auth/me`;
- la altura de la cabecera es la misma reservada que con sesión: 134,4 px a 1024 de ancho y 170,4 px a 375 y 412;
- el foco no entra en el hueco;
- el recorrido AUTH-02 funciona;
- a 375 px, sin scroll horizontal.

**Accessibility, comprobada por el usuario en el DOM servido** (2026-10-28, con el build de H2 en el 3003, ventana sin extensiones y JavaScript desactivado en `/suppliers`):

- **DOM:** el contenedor del hueco es `<div aria-hidden="true" inert class="invisible …">`, con 6 `<span>` sin `href` ni `<a>`, el hueco del email (`span.w-40`) y el botón «Cerrar sesión» `disabled` con `tabindex="-1"`.
- **Panel Accessibility de DevTools:** no consultado.
- **Prueba del Tab:** no hecha (confirmado por el usuario). Lo que consta es la comprobación del agente en H1 sobre el HTML del servidor sin scripts: el foco programático no entra en el botón reservado y sí en el enlace de la marca.

### H2 — esqueleto del resumen de `/incident-manager` (`4039279`)

El build medido es el de `4039279`, compilado desde PowerShell. 1 ejecución en la URL clave, en una ventana de invitado de Chrome.

**Comprobaciones:**

| Archivo | `finalDisplayedUrl` | `formFactor` | LH | `fetchTime` (UTC → local) | `benchmarkIndex` | `disableStorageReset` | `runWarnings` | `chrome-extension://` |
|---|---|---|---|---|---|---|---|---|
| `steps/H2/incident-manager-mobile.json` | `http://localhost:3003/incident-manager` | mobile | 13.4.1 | 2026-10-27 23:39:03Z → 2026-10-28 00:39:03 | 3640 | `true` (con sesión) | vacío | **0** |

**Resultados frente al antes y a H1:**

| | Perf | FCP | LCP | TBT | CLS | SI | FCP observado |
|---|---|---|---|---|---|---|---|
| antes | 82 | 0,6 s (613 ms) | 1,0 s (958 ms) | 24 ms | 0,373 | 0,6 s | 60 ms |
| H1 (con extensiones) | 88 | 0,9 s (922 ms) | 1,1 s (1132 ms) | 9 ms | 0,240 | 0,9 s | 178 ms |
| **H2** | **100** | 0,6 s (625 ms) | 0,9 s (917 ms) | 51 ms | **0** (0,0000449) | 0,6 s | 58 ms |

Accessibility, Best Practices y SEO: 100. El elemento LCP sigue siendo `main.mx-auto > div.flex > p.text-sm`, la descripción de la página.

**`layout-shifts`:**

| Medición | Desplazamientos |
|---|---|
| antes | sección del listado 0,2344 + `main.mx-auto` 0,1337 + filtros 0,0052 |
| H1 | sección del listado 0,2344 + filtros 0,0052 |
| **H2** | solo `div.flex > dl.flex > div.flex > dd.tabular-nums`, de **0,0000449** |

**Conclusión: H2 hace lo esperado, y algo más.**

- **El desplazamiento del listado (0,2344) desaparece.** El CLS pasa de 0,373 a 0 y la Performance de 82 a 100. Cumple el criterio (CLS < 0,1 y Performance ≥ 90).
- **El desplazamiento de los filtros (0,0052) también desaparece; no es un redondeo.** Ya no figura en `layout-shifts`. La causa probable es que la fila de filtros, dentro de la sección del listado, se recolocaba con el mismo empuje del resumen. El 0,0052 de suppliers (S5) es otro caso y no lo toca H2.
- **El único desplazamiento que queda vale 0,0000449,** y Lighthouse lo muestra como 0. Está en un `<dd>` del resumen: al cambiar «—» por el número, el ancho de la celda varía y se mueve unos píxeles en horizontal (`justify-between`). No requiere corrección.
- **El FCP vuelve a 0,6 s** (625 ms simulado, 58 ms observado), como en el antes. Confirma que la subida de H1 a 0,9 s se debía a las extensiones (§2, H1).

**Datos de desarrollo: «Synthetic ticket 028».** Durante la verificación de H2, el agente pasó esta incidencia de `open` a `in_progress` en la TinyDB de desarrollo. **No se puede restaurar**: el ciclo de vida solo permite `in_progress → resolved` o `in_progress → discarded`. Así lo fijan:

- `ALLOWED_TRANSITIONS` en `packages/shared/nexova_shared/incidents/rules.py`;
- `INCIDENT_TRANSITIONS` en `uis/backoffice/types/incident-manager.ts`;
- `docs/centralized-incident-manager.md`.

No se ha tocado el archivo de la base.

Desde entonces, los totales del resumen difieren del antes en ese ticket: `open` 26 en lugar de 27 e `in_progress` 2 en lugar de 1. `resolved` (56), `discarded` (13) y el total (97) no cambian. **No afecta al CLS ni a la altura:** el listado sigue con 97 filas y el resumen tiene las mismas 19 filas; solo cambian dos números.

## 3. Medición final

Hecha por el usuario el 2026-10-28, de 19:08 a 19:25 (hora local, UTC+1). Medida sobre el build de producción de `bd7d084`, que es el último commit de código (H1, H2, CRLF, H3, H4 y R1). 1 ejecución por caso, en una ventana de invitado de Chrome, sin extensiones.

### 3.1 Comprobaciones

Los 12 JSON cumplen:

- `finalDisplayedUrl` es la URL pedida;
- `formFactor` es el esperado;
- Lighthouse 13.4.1;
- `runWarnings` vacío;
- **0 peticiones `chrome-extension://`**;
- cada caso tiene su captura.

| Caso | Archivo | `fetchTime` (UTC → local) | `benchmarkIndex` (antes → después) | Ancho (antes → después) | `disableStorageReset` (antes → después) |
|---|---|---|---|---|---|
| 1 | `website/index/index-mobile` | 18:08:58Z → 19:08:58 | 3892,5 → 2472 | 412 → 412 | `false` → **`true`** |
| 2 | `website/index/index-desktop` | 18:10:34Z → 19:10:34 | 3728,5 → 2273,5 | **1526 → 870** | `false` → **`true`** |
| 3 | `website/application/application-mobile` | 18:11:47Z → 19:11:47 | 3862,5 → 2329,5 | 412 → 412 | `false` → **`true`** |
| 4 | `website/application/application-desktop` | 18:14:42Z → 19:14:42 | 3724,5 → 2136 | **1526 → 870** | `false` → **`true`** |
| 9 | `backoffice/login/login-mobile` | 18:16:08Z → 19:16:08 | 3825,5 → 2142,5 | 412 → 412 | `false` → `false` |
| 10 | `backoffice/login/login-desktop` | 18:17:30Z → 19:17:30 | 3730,5 → 2080,5 | **1526 → 870** | `false` → `false` |
| 6 | `backoffice/incident-manager/incident-manager-mobile` | 18:18:33Z → 19:18:33 | 3671,5 → 2269,5 | 412 → 412 | `true` → `true` |
| 5 | `backoffice/incident-manager/incident-manager-desktop` | 18:19:28Z → 19:19:28 | 3726,5 → 2282,5 | **1526 → 870** | `true` → `true` |
| 11 | `backoffice/suppliers/suppliers-mobile` | 18:20:19Z → 19:20:19 | 3833,5 → 2498,5 | 412 → 412 | `true` → `true` |
| 7 | `backoffice/suppliers/suppliers-desktop` | 18:23:08Z → 19:23:08 | 3569,5 → 2281 | **1526 → 870** | `true` → `true` |
| 12 | `backoffice/inventory-products/inventory-products-mobile` | 18:24:59Z → 19:24:59 | 3653,5 → 2433 | 412 → 412 | `true` → `true` |
| 8 | `backoffice/inventory-products/inventory-products-desktop` | 18:25:46Z → 19:25:46 | 3643 → 2329 | **1526 → 870** | `true` → `true` |

### 3.2 Diferencias de condiciones frente al antes

1. **La comparación desktop NO es homogénea.** El ancho sale de `fullPageScreenshot.screenshot.width`: 1526 px en el antes y 870 px en el después, en los 6 casos desktop. En ninguno de los dos lados hay emulación de pantalla (`screenEmulation.disabled`), así que el viewport es el ancho de la ventana. A 870 px el diseño cambia:
   - **La foto del index pasa a una sola columna** (la rejilla es de 2 columnas a partir de `lg`, 1024 px). Se muestra a 807×486 en lugar de 576×347, y el navegador elige el WebP de 1152 en lugar del de 768.
   - **Cambia el elemento LCP del index desktop:** antes era el logo (`img.h-10`) y ahora es el `h1` del hero.
   - **La navegación de la cabecera y la fila de filtros de `/suppliers` parten línea** de otra manera. De ahí salen los dos desplazamientos residuales de §3.4.

   Por eso la conclusión principal de la auditoría se apoya en los **6 casos móviles, que sí son homogéneos** (412 px en los dos lados). Los desktop se dan como complementarios.
2. **CPU más lenta.** El `benchmarkIndex` del después va de 2080,5 a 2498,5, frente a 3569,5–3892,5 en el antes: entre un 35 y un 45 % menos. Lighthouse aplica el mismo multiplicador de CPU (×4 en mobile) sobre una máquina más lenta, así que todo lo que es trabajo de CPU sube:
   - el **TBT** del backoffice mobile, de 24–78 ms a 101–134 ms. Todos siguen por debajo de 200 ms, y por eso la Performance de esas vistas es 99 y no 100;
   - el trabajo del hilo principal y el `bootup-time`, por ejemplo en incident-manager mobile: de 772 a 1306 ms y de 341 a 595 ms.

   **No dependen de la CPU** el CLS (es geometría y orden de pintado), los bytes transferidos ni el TTFB.
3. **«Clear storage» desmarcado en el sitio.** Los 4 casos del sitio tienen `disableStorageReset: true` en el después, frente a `false` en el antes. **No tiene efecto:** el servidor local envía `Cache-Control: no-store`, y todos los recursos del sitio se transfirieron completos (`transferSize` mayor que el tamaño del recurso en los 5 del index).

### 3.3 Resultados

Valores de los JSON. FCP y LCP en segundos, con un decimal; TBT en ms. Accessibility, Best Practices y SEO: 100 en los 12 casos, antes y después.

| # | App | Página | Modo | Perf | FCP | LCP | TBT | CLS | Peso total |
|---|---|---|---|---|---|---|---|---|---|
| 1 | website | index | mobile | 98 → **100** | 1,9 → **0,9** | 2,1 → **1,2** | 15 → 72 | 0 → 0 | 376 → **79 KiB** |
| 3 | website | application | mobile | 98 → **100** | 1,9 → **0,9** | 2,0 → **1,3** | 25 → 6 | 0 → 0 | 93 → **54 KiB** |
| 9 | backoffice | login | mobile | 100 → 99 | 0,8 → 0,8 | 1,7 → 1,6 | 23 → 101 | 0 → 0 | 174 → 175 KiB |
| 6 | backoffice | incident-manager | mobile | 82 → **99** | 0,6 → 0,6 | 1,0 → 1,0 | 24 → 134 | 0,373 → **0** | 25 → 27 KiB |
| 11 | backoffice | suppliers | mobile | 95 → **99** | 0,6 → 0,6 | 1,1 → 1,0 | 78 → 125 | 0,136 → **0,003** | 22 → 24 KiB |
| 12 | backoffice | inventory/products | mobile | 95 → **99** | 0,6 → 0,7 | 0,9 → 1,0 | 58 → 122 | 0,135 → **0,001** | 26 → 29 KiB |
| 2 | website | index | desktop* | 100 → 100 | 0,5 → 0,2 | 0,5 → 0,3 | 0 → 0 | 0 → 0 | 377 → 125 KiB |
| 4 | website | application | desktop* | 100 → 100 | 0,5 → 0,2 | 0,5 → 0,3 | 0 → 0 | 0 → 0 | 93 → 54 KiB |
| 10 | backoffice | login | desktop* | 100 → 100 | 0,2 → 0,2 | 0,4 → 0,4 | 0 → 0 | 0,003 → 0 | 174 → 175 KiB |
| 5 | backoffice | incident-manager | desktop* | 100 → 100 | 0,2 → 0,2 | 0,3 → 0,3 | 0 → 0 | 0,032 → 0 | 25 → 25 KiB |
| 7 | backoffice | suppliers | desktop* | 100 → 99 | 0,2 → 0,2 | 0,2 → 0,3 | 0 → 2 | 0,032 → 0,071 | 22 → 22 KiB |
| 8 | backoffice | inventory/products | desktop* | 100 → 100 | 0,2 → 0,2 | 0,2 → 0,3 | 0 → 0 | 0,032 → 0,026 | 27 → 27 KiB |

\* Desktop: 1526 px en el antes y 870 px en el después; comparación no homogénea (§3.2).

**Atribución por auditorías:**

- **H3 (Tailwind):** el script del CDN desaparece de `render-blocking-insight` en los 4 casos del sitio. El único recurso bloqueante es `styles.css`, con un ahorro estimado de 50 ms en index mobile y 0 en el resto (antes, 300–1150 ms). `unused-javascript` ya no aparece en el index (antes, 21 KiB).
- **H4 (foto):** `total-byte-weight` del index baja de 376 a 79 KiB en mobile y de 377 a 125 KiB en desktop. Se transfiere el WebP de 768 (43 KB) en mobile y el de 1152 (91 KB) en desktop a 870 px, en lugar del JPEG de 308 KB. `image-delivery-insight` pasa de 295 a 26 KiB en mobile y de 274 a 45 KiB en desktop (residual en §3.4).
- **H1 y H2:** se atribuyen por sus mediciones intermedias (§2). En la final, el CLS de las tres vistas móviles con datos queda en 0, 0,003 y 0,001, y en `layout-shifts` ya no aparecen ni `main.mx-auto` (H1) ni la sección del listado (H2).

### 3.4 Residuales (no son regresiones de las correcciones)

| Caso | Valor | Nodo (`layout-shifts`) | Causa | Posible arreglo (trabajo futuro, no aplicado) |
|---|---|---|---|---|
| suppliers desktop | CLS 0,071 | `div[role="group"][aria-label="Filtros del directorio"]` | La cabecera del directorio (`supplier-directory-view.tsx`) pone el título y los filtros en una fila con `flex-wrap justify-between`. Cuando llega el listado aparece el contador («15 proveedores · … con renovación…»), el bloque del título se ensancha y, a 870 px, los filtros pasan a la línea siguiente. **En el antes no iba sumado a la cabecera:** el CLS total desktop era 0,0323, exactamente el desplazamiento de la cabecera. Es el mismo nodo que el residual S5 de mobile (0,0026), que aquí pesa más porque la fila se mueve entera de línea | Reservar la línea del contador antes de que llegue el listado (un marcador con la misma altura), o poner los filtros siempre en su propia línea |
| inventory/products desktop | CLS 0,026 | `header … nav > button` («Cerrar sesión») | Residual 3 de H1: el hueco del email en la navegación reservada mide `w-40` (160 px), y el email real de la sesión es más ancho. Al llegar `/auth/me`, el botón se desplaza dentro de la navegación, que a 870 px ocupa dos líneas | Dar al email la misma anchura que el hueco (`w-40` + `truncate`, con el email completo en `title`), para que el ancho no dependa del email |
| index (H4) | `image-delivery-insight` 26 KiB (mobile) / 45 KiB (desktop) | Según la auditoría: el WebP de 768×462 «mostrado» a 475×286 en mobile y el de 1152×694 a 807×486 en desktop a 870 px | El `srcset` solo tiene dos anchos (768 y 1152), así que el navegador elige el más cercano por arriba al ancho que necesita | Añadir una variante intermedia (p. ej. 480 o 640 px), si el ahorro lo justifica |

Ninguno supera el umbral: CLS < 0,1 y ninguna auditoría con ahorro en métricas. Los dos de CLS dependen del ancho de la ventana; con el ancho del antes (1526 px) no se sabe si aparecen, porque no se midió.

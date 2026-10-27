# Website

Sitio web público de **Nexova Solutions** (Hito 1, Marketing y Comunicación, Carmen Ruiz): la landing (`index.html`) y el formulario de registro de talento (`application.html`), más la página de error (`404.html`). HTML estático, Tailwind CSS v4 y JavaScript sin dependencias (`src/js/nav.js`, `src/js/validations.js`). El envío del formulario se simula en `validations.js`: no hay backend.

## Estructura

| Ruta | Qué es |
|---|---|
| `index.html`, `application.html`, `404.html` | Las tres páginas |
| `src/css/tailwind.css` | Entrada de Tailwind (no se enlaza) |
| `src/css/styles.css` | CSS generado y minificado, **versionado**; es el que enlazan las páginas |
| `src/js/` | Menú móvil (`nav.js`) y validación del formulario (`validations.js`) |
| `src/img/` | Logo y foto |

## Arrancar

- **Desarrollo:** con Docker, en `http://localhost:3000` (`docker compose up` desde la raíz; ver [`docs/local-development.md`](../../docs/local-development.md)). Lo sirve [`uis/serve-website.mjs`](../serve-website.mjs).
- **Producción:** Netlify publica esta carpeta tal cual ([`netlify.toml`](../../netlify.toml)). **No hay build en el despliegue**, así que `styles.css` tiene que estar regenerado y comiteado.

## CSS: Tailwind precompilado

Desde la auditoría de rendimiento (H3 de [`AUDIT.md`](../../AUDIT.md)), el sitio ya no usa el Play CDN de Tailwind. Aquel script generaba el CSS en el navegador y bloqueaba el primer pintado. Ahora el CSS se genera con el CLI de Tailwind, en una versión fija, y se sirve como un archivo local.

**Hay que regenerarlo** cada vez que se añada o cambie una clase en los HTML o en `src/js/` (por ejemplo, las que `validations.js` añade o quita en tiempo de ejecución). `tailwind.css` declara qué se escanea (`source(none)` y dos `@source`), así que una clase en otro archivo no entra.

**Comando**, desde `uis/website`. No añade `package.json` ni dependencias al repo: instala el CLI, en versión fija, en una carpeta temporal fuera del repo.

- PowerShell:

  ```powershell
  $tw = Join-Path $env:TEMP 'nexova-tailwind'
  npm install --prefix $tw --no-audit --no-fund @tailwindcss/cli@4.3.3 tailwindcss@4.3.3
  $env:NODE_PATH = Join-Path $tw 'node_modules'
  & (Join-Path $tw 'node_modules\.bin\tailwindcss.cmd') -i src/css/tailwind.css -o src/css/styles.css --minify
  Remove-Item Env:NODE_PATH
  ```

- bash:

  ```bash
  tw="${TMPDIR:-/tmp}/nexova-tailwind"
  npm install --prefix "$tw" --no-audit --no-fund @tailwindcss/cli@4.3.3 tailwindcss@4.3.3
  NODE_PATH="$tw/node_modules" "$tw/node_modules/.bin/tailwindcss" -i src/css/tailwind.css -o src/css/styles.css --minify
  ```

**Por qué `NODE_PATH`:** el CLI resuelve `@import "tailwindcss"` buscando `node_modules` desde la carpeta de `tailwind.css` hacia arriba, y en este repo no hay ninguno (ni debe haberlo: el sitio no tiene dependencias). `@tailwindcss/node` añade `NODE_PATH` a las carpetas donde busca. Por la misma razón, `npx @tailwindcss/cli` a secas no encuentra el paquete.

**Versión:** la 4.3.3, la misma que servía el Play CDN (`@tailwindcss/browser@4`) cuando se midió la auditoría. Si se cambia, hay que repetir la comparación visual.

**Después de regenerar:**

- comprobar a la vista las tres páginas en desktop y a 375 px, con el menú móvil abierto y cerrado y el formulario en estado de error y de éxito;
- comitear `styles.css` junto con el cambio de HTML o JS que lo motivó.

## Validación

No tiene build ni tests propios (`AGENTS.md` §4): se verifica a mano, en el navegador. El servidor de desarrollo sí tiene tests, que se ejecutan desde la raíz con `node --test "uis/tests/*.test.mjs"`.

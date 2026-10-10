@AGENTS.md

# Talent Pipeline Tracker — Restricciones permanentes

Fuente de verdad: `SPECS.md` (raíz del proyecto). Ante cualquier duda no cubierta aquí ni en SPECS.md, pregunta — no asumas.

## Stack
- Next.js (App Router), TypeScript estricto, Tailwind CSS v4 (config vía CSS, sin `tailwind.config.ts`).
- Estado: solo hooks nativos de React (`useState`, `useReducer`, `useContext`, `useOptimistic`, hooks propios). Prohibido Redux, Zustand, Recoil, Jotai u otra librería de estado.
- No añadir ninguna dependencia nueva sin autorización explícita.

## Tipos
- Prohibido `any` en todo el proyecto.
- `unknown` solo se permite en `services/normalizers.ts` (frontera de confianza red → tipos firmes).
- Prohibido usar `as` para forzar el tipo de una respuesta de red.

## Contrato con la API
- Prohibido inventar campos, endpoints o formas de respuesta que no estén en `SPECS.md` (OpenAPI o contrato observado §4.8). Si falta algo, pregunta antes de asumir.
- La API usa tres formatos de envoltorio distintos entre endpoints (§4.8.4): un normalizador por endpoint en `services/normalizers.ts`, nunca uno genérico.
- Nunca establecer `credentials` en `fetch` (§5.1): el CORS de la API combina `Allow-Origin: *` con `Allow-Credentials: true` (inválido); el navegador rechaza la petición si se envían credenciales.

## Arquitectura
- Los componentes nunca hacen llamadas HTTP directas: toda petición pasa por `services/`.
- Client Components para listado y detalle; fetch desde el navegador, sin Route Handlers ni proxy.

## Errores (SPECS.md §5.4)
- **Límites de error (Next 16):**
  - `app/error.tsx` se muestra dentro del layout raíz. `app/global-error.tsx` solo actúa si falla el propio layout raíz: tiene su propio `<html>`/`<body>`, importa `globals.css` y no usa ni la sesión, ni el guard, ni los avisos. `app/not-found.tsx` cubre las rutas inexistentes y `app/candidates/[id]/not-found.tsx` sigue cubriendo el 404 de una candidatura.
  - Textos fijos en español y enlace a `/`. Los límites de error son Client Components con «Reintentar», que llama a `retry()`. Firma de props de Next 16.3: `{ error: Error & { digest?: string }; retry: () => void }`.
  - **El error no se lee:** ni `console.*`, ni `error.message`, `digest` o `stack`.
- **Textos para el usuario:**
  - Siempre con `describeApiError` (`lib/api-client.ts`), que da un texto fijo por tipo de error (`classifyApiError`: red, timeout, 401, 404, 4xx, 5xx, respuesta ilegible y desconocido).
  - Nunca se muestra el código HTTP, el mensaje de un normalizador (`ResponseShapeError`, en `lib/response-shape-error.ts`) ni `String(error)`. Solo el 422 muestra los `msg` de la API.
  - Los hooks guardan el error con `asError`, que conserva su clase, en vez de convertirlo en texto.
  - Lo comprueba `tests/production-source.test.mjs`.
- **Guardar una candidatura:** el error se clasifica con `classifySubmitError` (`lib/submit-error.ts`).
  - Un 2xx con cuerpo ilegible o fuera de contrato significa «se guardó, recarga el listado». Un timeout significa «no se sabe si se guardó».
  - En los dos casos se bloquea el reenvío para no duplicar la candidatura.
  - El `<dialog>` de `components/ui/modal.tsx` no desmonta su contenido al cerrarse: cada apertura del modal monta un `CandidateForm` nuevo (`key` renovada en `openCreate`/`openEdit`), para que el bloqueo y los errores no pasen al siguiente intento. Lo comprueba `tests/production-source.test.mjs`.
- **Timeout:** cubre la petición y la lectura del cuerpo (`response.json()`).
- **Fail-fast de §3.2:** se mantiene sin cambios. Sin `NEXT_PUBLIC_API_URL`/`NEXT_PUBLIC_AUTH_API_URL`, `npm run build` falla al prerenderizar. En `next dev`, la app muestra `global-error.tsx` y el overlay de desarrollo de Next muestra el mensaje con la variable que falta.

## Autenticación (AUTH-02, SPECS.md §9)
- La sesión se obtiene de `services/api` de Nexova (`NEXT_PUBLIC_AUTH_API_URL`), no de la API de 4Geeks, que nunca recibe el token.
- El JWT se guarda en `localStorage` (exigido por el ticket) y solo `lib/auth-token.ts` lo toca. No se persiste nada más en el navegador.
- `Authorization: Bearer` y el tratamiento del 401 viven solo en `lib/api-client.ts` (`authApiClient`); las vistas no repiten esa lógica.
- Protección global con el guard del layout raíz (`lib/auth-routes.ts`): toda vista nueva es protegida por defecto. Prohibido usar middleware/proxy de Next.js o cookies para comprobar la sesión.
- Contraseñas (AUTH-03, SPECS.md §9.4): `/forgot-password` pública, `/reset-password` abierta (`OPEN_PATHS`), `/account/change-password` protegida. La confirmación nunca se envía a la API y `/forgot-password` no distingue si el email existe.

## Tono e identidad
- Esto es una herramienta interna de Nexova Solutions (Operaciones de Selección), no una app genérica: sobria, funcional, orientada a eficiencia operativa, coherente con el contexto y la imagen de la empresa.

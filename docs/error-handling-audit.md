# Auditoría de gestión de errores — informe y guía de revisión

Documento para revisar la auditoría de gestión de errores: qué se encontró, qué se corrigió en cada capa, qué cambia para el usuario, cómo se demuestra cada criterio del ticket y cómo verificarlo.

- Rama: `feature/error-handling-audit`, que sale de `main` en `6dfa013` (merge de la PR #17).
- Historial por fases y validaciones ejecutadas: [`memory-bank/progress.md`](../memory-bank/progress.md) (entradas del 2026-10-10).
- Decisiones técnicas permanentes: [`memory-bank/techContext.md`](../memory-bank/techContext.md), sección «Gestión de errores».
- Reglas por subproyecto. Aquí no se repiten, solo se enlazan:
  - [`services/api/SPECS.md`](../services/api/SPECS.md): §4 y §5 (formato de errores y privacidad, con el 503 `storage_unavailable`), §12, §18, §31 y §33;
  - [`uis/backoffice/CLAUDE.md`](../uis/backoffice/CLAUDE.md), sección «Arquitectura»: límites de error y textos sin detalles técnicos;
  - [`uis/talent-pipeline-tracker/CLAUDE.md`](../uis/talent-pipeline-tracker/CLAUDE.md), sección «Errores», y [`SPECS.md`](../uis/talent-pipeline-tracker/SPECS.md) §5.4.

## 1. Contexto

### El ticket (texto literal)

> «Tu tech lead ha abierto un ticket de revisión de código con un mensaje claro: el sistema no tiene una estrategia coherente de gestión de errores. Las llamadas a la API pueden fallar en silencio, faltan estados de carga, los usuarios ven mensajes técnicos crudos (o simplemente nada), y los scripts de fondo se rompen sin dejar rastro útil. Antes de que el siguiente hito introduzca más complejidad, el equipo necesita corregir esto.»
>
> «Tu tarea es auditar todo el repositorio existente y aplicar una estrategia de gestión de errores consistente en todas las capas: frontend, backend y scripts.»

**Lo que necesitamos (notas del tech lead, literal):**

- Ningún error debe romper la aplicación ni dejar al usuario en un estado indefinido.
- Toda operación asíncrona en el frontend debe tener tres estados visibles: cargando, éxito y error.
- Los mensajes de error que ve el usuario deben ser legibles — nunca un stack trace, un código de estado o un error de parseo de JSON en crudo.
- Todo estado de error debe ofrecer una salida clara: un botón de reintentar, un enlace a la página principal o instrucciones para contactar soporte.
- En el backend y los scripts, las excepciones deben capturarse en el ámbito correcto — no con un único try/catch que envuelva toda la función.
- Nunca debe aparecer información sensible en la salida de errores enviada al cliente.

> «Esta es una tarea de ingeniería transversal — no una nueva funcionalidad. El entregable es una versión más limpia y robusta del repositorio que ya has construido. Al terminar este proyecto, cualquier usuario que encuentre un problema en tu plataforma sabrá qué ha pasado y qué puede hacer.»
>
> Nota de evaluación: «La evaluación se centra en la corrección y consistencia de los patrones de gestión de errores; no en si se añadieron nuevas funcionalidades.»

### Alcance: cinco capas

| Capa | Qué se revisó |
|---|---|
| Backend | `services/api/app`: `core/errors.py`, `core/limits.py`, `routes/`, `auth/` (con el envío a Resend), `modules/incidents`, `modules/incident_manager` y `database.py` |
| Scripts y CLIs | `scripts/analyze.py`, `scripts/seed_incidents.py`, `services/api/app/seed.py` (`uv run seed`), `services/api/app/auth/create_admin.py`, y `packages/incident-analyzer` y `packages/shared` en lo que afecta a esos scripts |
| Backoffice | `uis/backoffice`: `/incidents`, `/suppliers`, `/incident-manager` y autenticación |
| Tracker | `uis/talent-pipeline-tracker`: candidaturas, notas y autenticación |
| Web | `uis/website` (HTML estático) |

## 2. Metodología

**Primero, una auditoría de solo lectura** (2026-10-09) de todo el código de producción, sin los tests. Cada hallazgo indica:
- archivo y línea;
- categoría y severidad;
- si se **verificó** leyendo el código o es una **suposición**;
- la corrección propuesta y si choca con alguna regla (`CLAUDE.md`, `SPECS.md` o tests estáticos).

Después se corrigió por fases, **un commit por capa**. Cada fase pasó tres comprobaciones: las validaciones de [`AGENTS.md`](../AGENTS.md) §4, una mutación por arreglo (se deshace y el test nuevo tiene que fallar) y una verificación manual.

**Las 9 categorías:**

| # | Categoría |
|---|---|
| 1 | Try/catch ausente en operaciones asíncronas o de E/S |
| 2 | Catch demasiado amplio (envuelve funciones enteras) |
| 3 | Fallos silenciosos (errores capturados e ignorados) |
| 4 | Exposición de errores en crudo (mensajes, trazas o códigos HTTP en la UI o en la respuesta) |
| 5 | Filtración de datos sensibles (secretos, rutas internas, emails o filas del CSV) |
| 6 | Estados de carga o error ausentes en la UI (incluidos `error.tsx`, `global-error.tsx` y `not-found.tsx`) |
| 7 | Sin llamada a la acción (sin reintentar, sin enlace a inicio, sin contacto) |
| 8 | Sin código de salida en el fallo de un script |
| 9 | Limpieza del estado de carga sin `finally` |

**Severidades:**
- **CRÍTICO:** fuga de datos o caída general.
- **ALTO:** pantalla rota sin salida.
- **MEDIO:** fallo real con impacto acotado.
- **BAJO:** mejora de claridad o robustez.

**«Correcto por diseño»:** un patrón que parece un fallo pero existe a propósito. Se comprobó que sigue cumpliendo su intención y se listó aparte (§3.2), sin corregirlo.

## 3. Informe de la auditoría

Resultado: **0 críticos, 2 altos, 6 medios y 10 bajos**. Se corrigieron 16 de 18; los otros 2 se descartaron con motivo (§6).

### 3.1 Hallazgos

| ID | Sev. | Cat. | Archivo | Problema | Corrección aplicada | Commit | Estado |
|---|---|---|---|---|---|---|---|
| A1 | MEDIO | 1, 3 | `services/api/app/auth/email.py` | `send()` no capturaba `http.client.HTTPException` (`IncompleteRead`, `BadStatusLine`, `LineTooLong`): escapaba de la tarea en segundo plano y la registraba el middleware del 500 | Se añade a los errores que pasan a `EmailDeliveryError` (`from None`); se registra con `log_email_delivery_failure` | `24f0e0d` | Hecho |
| A2 | MEDIO | 1 | Repositorios TinyDB (`database.py`, `auth/repository.py`, `modules/incident_manager/repository.py`) | Un archivo ilegible o corrupto daba un 500 genérico sin saber qué base fallaba; con `auth.json` dañado caían el login y todas las rutas protegidas | `GuardedJSONStorage` (`app/core/storage.py`) → 503 `storage_unavailable`, con captura solo en las operaciones de archivo; registro solo del almacén y la clase | `24f0e0d` | Hecho |
| S1 | MEDIO | 8, 1 | `scripts/seed_incidents.py` | La escritura en la base no estaba protegida: un traceback incumplía los códigos 0/1/2 del docstring | `try` solo alrededor de `seed()`, capturando `StorageUnavailableError` → código 2 y mensaje sin ruta completa | `a6f3722` | Hecho |
| S2 | BAJO | 8 | `services/api/app/seed.py` | `ConfigError` y errores de la base acababan en traceback | Dos `try` separados → `sys.exit(1)` con mensaje en stderr | `a6f3722` | Hecho |
| S3 | BAJO | 8 | `services/api/app/auth/create_admin.py` | `ConfigError`, `EOFError`/Ctrl+C y errores de la base acababan en traceback | Capturas separadas → código 1, sin crear nada ni mostrar la contraseña | `a6f3722` | Hecho |
| S4 | BAJO | 8 | `scripts/analyze.py` | Ctrl+C en la pregunta de exportar daba un traceback; `strerror` podía mostrar «None» | Ctrl+C equivale a «no exportar»; `describe_os_error`, también en `seed_incidents.py` | `a6f3722` | Hecho (sin `BrokenPipeError`, §6) |
| B1 | ALTO | 6, 7 | `uis/backoffice/app/` | Sin `error.tsx`, `global-error.tsx` ni `not-found.tsx`: un fallo de render dejaba la pantalla genérica de Next | Los tres archivos, con textos fijos, «Reintentar» (`retry()`) y enlace a inicio; no leen el error | `2454dcd` | Hecho |
| B2 | BAJO | 4, 5 | `components/{suppliers,incident-manager,auth,incidents}/*-error.tsx` y `supplier-directory-view.tsx` | Los avisos mostraban «(422)», «services/api» y «NEXT_PUBLIC_API_URL» | Textos neutros con una acción; test estático que lo prohíbe | `2454dcd` | Hecho |
| B3 | BAJO | 6 | `hooks/use-auth-session.ts`, `components/auth/auth-guard.tsx` | «Reintentar» del guard no mostraba carga y el texto era el mismo para cualquier error | `validation_started` → `retrying` y `sessionErrorCopy` según el tipo de error | `2454dcd` | Hecho |
| B4 | BAJO | 1 | `uis/backoffice/lib/api-client.ts` | `blob()` no traducía un fallo de lectura: salía «respuesta inesperada» en lugar de «sin conexión» | Mismo tratamiento que `json()`: abort se relanza, el resto pasa a `ApiNetworkError` | `2454dcd` | Hecho |
| B5 | BAJO | 7 | Avisos de error del backoffice | Ningún aviso ofrecía contacto con soporte | — | — | No se hace (§6) |
| T1 | ALTO | 6, 7 | `uis/talent-pipeline-tracker/app/` | Sin límites de error ni `not-found.tsx` raíz | Los tres archivos; se conserva `candidates/[id]/not-found.tsx`; el fail-fast de SPECS §3.2 no cambia | `dc91918` | Hecho |
| T2 | MEDIO | 4 | `lib/api-client.ts`, `candidate-list`, `candidate-detail`, `notes-list`, `candidate-form`, hooks | La UI mostraba «La API respondió con el código 500», los mensajes de los normalizadores y `String(error)` | `describeApiError` con un texto fijo por tipo; `ResponseShapeError`; `asError` en los hooks | `dc91918` | Hecho |
| T3 | MEDIO | 1, 9 | `uis/talent-pipeline-tracker/lib/api-client.ts` | El timeout se cancelaba al recibir las cabeceras: un cuerpo colgado dejaba la vista cargando para siempre | El timeout cubre también `response.json()` (`readJson`) | `dc91918` | Hecho |
| T4 | MEDIO | 4, 3 | `components/candidates/candidate-form.tsx` | Un 2xx con cuerpo ilegible tras un POST/PUT se mostraba como «No se pudo conectar», y el usuario reintentaba y duplicaba la candidatura | `classifySubmitError` (`lib/submit-error.ts`); el reenvío se bloquea en «se guardó» y en timeout; cada apertura del modal monta un formulario nuevo | `dc91918` | Hecho |
| T5 | BAJO | 9 | `uis/talent-pipeline-tracker/lib/api-client.ts` | `request()` no acepta una señal de cancelación externa | — | — | No se hace (§6) |
| T6 | BAJO | 6 | `hooks/use-auth-session.ts`, `components/auth/auth-guard.tsx` | El mismo problema que B3 | El mismo patrón que B3 | `dc91918` | Hecho |
| W1 | BAJO | 6, 7 | `uis/website/` | Sin `404.html`: Netlify mostraba su 404 genérico | `404.html` con la misma cabecera y pie, enlace a inicio y al formulario, y rutas absolutas | `899ce1e` | Hecho |

### 3.2 Revisado, correcto por diseño

Se comprobó que cada patrón sigue cumpliendo su intención; no se corrigió nada.

1. **`except UnicodeDecodeError: pass` seguido de `raise IncidentFileError` fuera del `except`** (`incident_analyzer/analyze.py:36-44`, `scripts/seed_incidents.py:71-76`): evita encadenar los bytes leídos, que pueden contener emails.
2. **`except Exception` del middleware del 500** (`services/api/app/core/errors.py:220-221`): es la frontera final del proceso y solo registra el nombre de la clase.
3. **El 400 `{code: validation_error, detail: [...]}` de `/api/incidents`** en lugar del 422 (SPECS Parte E): solo usa la ubicación del error de FastAPI, nunca `input` ni `msg`.
4. **El `try`/`catch` de `lib/auth-token.ts` en las dos apps**: sin almacenamiento disponible, la app se comporta como «sin sesión».
5. **El `catch` de `new URL()`** en `uis/website/src/js/validations.js`.
6. **El envío simulado del formulario de la web**: lo pide el contexto del Hito 1.
7. **Los `print` de `app/seed.py` y `create_admin.py`**: los permite `test_architecture.py`, y no imprimen la contraseña.
8. **El `msg` del 422 en la UI de proveedores, auth y tracker**: lo permiten los `CLAUDE.md` y SPECS §5.4, y los validadores no repiten la entrada.
9. **El `detail` de `invalid_csv` en `/incidents`**: el lector solo cita columnas y números de fila.
10. **`boardView` («el error manda») en `/incident-manager`**: está fijado por el `CLAUDE.md` del backoffice.
11. **Los errores del email de recuperación solo se registran**, en segundo plano, para no revelar qué emails existen.
12. **Los 4 errores de lint `react-hooks/set-state-in-effect` del tracker**: son anteriores a esta rama y quedan fuera de alcance.

## 4. Qué cambió

### 4.1 Por capa

| Capa | Commit | Cambios principales |
|---|---|---|
| Backend | `24f0e0d` | `app/core/storage.py` (nuevo); `StorageUnavailableError` y `log_storage_failure` en `core/errors.py`; `email.py`; tests `test_storage.py` y casos nuevos en `test_password_reset.py` |
| Scripts | `a6f3722` | `seed_incidents.py`, `analyze.py`, `app/seed.py` y `create_admin.py`; tests en `test_incident_manager_seed.py`, `test_suppliers_seed.py`, `test_create_admin.py` y `packages/incident-analyzer/tests/test_cli_errors.py` |
| Backoffice | `2454dcd` | `app/error.tsx`, `global-error.tsx` y `not-found.tsx`; textos de error; `use-auth-session.ts`, `auth-guard.tsx` y `auth-routes.ts`; `blob()` en `api-client.ts`; tests `production-source`, `api-client` y `use-auth` |
| Tracker | `dc91918` | Los tres límites de error; `api-client.ts` (clasificación, textos y timeout); `lib/response-shape-error.ts` y `lib/submit-error.ts` (nuevos); normalizadores; hooks; `candidate-form`, `candidate-list`, `candidate-detail` y `notes-list`; guard; tests `errors.test.mjs` y `production-source.test.mjs` |
| Web | `899ce1e` | `uis/website/404.html` |
| Docs | `e99e6a2` y este | Memory-bank y este documento |

### 4.2 Para el usuario: antes y ahora

| Situación | Antes | Ahora |
|---|---|---|
| Un archivo de base de datos corrupto | 500 genérico; con `auth.json` dañado no se podía ni iniciar sesión, sin pista de la causa | 503 `storage_unavailable`. El backoffice lo muestra como «Error del servidor», el guard como «El servidor tuvo un problema al comprobar tu sesión…» y el log dice qué almacén falla |
| Un script con la base dañada, Ctrl+C o configuración incompleta | Traceback de Python | Una línea en stderr con qué revisar y un código de salida |
| Un error de render en cualquier vista | Pantalla genérica de Next, en inglés y sin salida | «Algo ha fallado», con «Reintentar» y enlace a inicio |
| Una ruta inexistente | 404 por defecto de Next o de Netlify | Página «no encontrada» en español, con enlace a inicio (y al formulario, en la web) |
| La API caída o lenta (backoffice) | Textos con «services/api», «NEXT_PUBLIC_API_URL» o «(422)» | Textos neutros: «No se pudo conectar con el servidor. Comprueba tu conexión e inténtalo de nuevo…» |
| La API caída, un 500 o un cuerpo colgado (tracker) | «La API respondió con el código 500», mensajes de normalizador o carga infinita | Un texto fijo por tipo y «Reintentar»; un cuerpo colgado termina en «El servidor tardó demasiado…» |
| Crear una candidatura cuando el POST responde 2xx con cuerpo ilegible | «No se pudo conectar»; el usuario reintentaba y la duplicaba | «Se guardó, pero no se pudo leer la respuesta; recarga el listado.» y el botón de enviar se deshabilita |
| Abrir «Nueva candidatura» | Conservaba lo escrito, incluso después de crear una | **Se abre siempre vacía** (cada apertura monta un formulario nuevo) |
| «Reintentar» en el guard de sesión | Sin señal de carga y el mismo texto para cualquier error | «Reintentando…» con spinner y botón deshabilitado; un texto según el tipo de error |

## 5. Trazabilidad: «Qué vamos a evaluar»

En `main` = ya existía antes de esta rama. **Rama** = lo añade esta rama.

### 5.1 Todas las operaciones asíncronas del frontend implementan el patrón de UI de tres estados (cargando / éxito / error)

**Backoffice.** Todas las operaciones asíncronas viven en `hooks/`; ningún componente hace `await` directamente. Cada fila es: acción de carga → éxito / error.

| Hook · operación | Cargando | Éxito / error | Origen |
|---|---|---|---|
| `use-incident-analysis.ts` · analizar | `analysis_started` :216 | :224 / :227 | `main` |
| `use-incident-analysis.ts` · exportar | `export_started` :245 | :256 / :259 | `main` |
| `use-supplier-directory.ts` · listar | `list_started` :211 | :221 / :224 | `main` |
| `use-supplier-directory.ts` · fila | `row_started` :238 | :244 / :247 | `main` |
| `use-supplier-directory.ts` · alta | `create_started` :286 | :292 / :297 | `main` |
| `use-incident-board.ts` · listar | :184 | :193 / :196 | `main` |
| `use-incident-board.ts` · cambio de estado | :232 | :238 / :243, con reversión | `main` |
| `use-incident-summary.ts` | :77 | :82 / :85 | `main` |
| `use-incident-form.ts` | :93 | :98 / :101 | `main` |
| `use-auth-form.ts` | :72 | :76 / :80 | `main` |
| `use-profile.ts` · cargar | :97 | :101 / :104 | `main` |
| `use-profile.ts` · guardar | :131 | :135 / :138 | `main` |
| `use-auth-session.ts` · validar | `checking` (derivado) y **`retrying` :158** | `validated` / `failed` | **Rama**: `retrying` |

**Tracker:**

| Hook o componente | Cargando | Éxito / error | Origen |
|---|---|---|---|
| `use-records.ts` | :90 | `success`/`empty` :96 / :106 | `main` (**rama**: error tipado) |
| `use-record-detail.ts` | :36 | :41, `not-found` :46 / :50 | `main` (**rama**: error tipado) |
| `use-notes.ts` · cargar | :46 | :51 / :57 | `main` |
| `use-notes.ts` · añadir / borrar | `isAddingNote` :74 / `deletingNoteId` :98 | `true` / `addNoteError`, `deleteNoteError` | `main` |
| `use-profile.ts` · cargar / guardar | :26, :46 / `isSaving` :60 | :38 / :41 · `true` / `saveErrors` | `main` |
| `use-auth-form.ts` | `isSubmitting` :46 | `onSuccess` / `setErrors` | `main` |
| `use-auth-session.ts` | `checking` y **`retrying` :113** | :119 / :125 | **Rama** |
| `candidate-form.tsx` | `isSubmitting` :131 | aviso de éxito / `classifySubmitError` | **Rama**: clasificación |
| `candidate-status-controls.tsx` | `useTransition` (`isPending` :59), optimista | `committed` / aviso con reversión | `main` |

**Tests:** `use-incident-analysis`, `use-supplier-directory`, `use-incident-manager`, `use-auth` (backoffice); `errors.test.mjs` → «T6: reintento del guard…» (tracker).

### 5.2 Los mensajes de error mostrados al usuario son legibles e incluyen una llamada a la acción

- **Backoffice (rama):**
  - textos neutros en `components/{auth/auth-error, incidents/analysis-error, suppliers/supplier-error, incident-manager/incident-error}.tsx`;
  - `sessionErrorCopy` en `hooks/use-auth-session.ts`;
  - «Reintentar», «Ir a la página principal» y «Cerrar sesión» en `app/error.tsx`, `app/global-error.tsx`, `app/not-found.tsx` y `components/auth/auth-guard.tsx`;
  - los «Reintentar» de los listados ya existían en `main`.
- **Tracker (rama):**
  - `API_ERROR_MESSAGES` y `describeApiError` en `lib/api-client.ts`;
  - `SAVED_BUT_UNREADABLE_MESSAGE` y `UNCERTAIN_OUTCOME_MESSAGE` en `lib/submit-error.ts`;
  - los tres límites de error y el guard.
- **Web (rama):** `uis/website/404.html`, con «Volver al inicio» e «Ir al formulario de candidatura».
- **Tests:**
  - backoffice `production-source.test.mjs`: «ningún texto de components/ ni app/ muestra detalles técnicos»;
  - backoffice `use-auth.test.mjs`: «cada tipo de error tiene su texto, sin detalles técnicos»;
  - tracker `errors.test.mjs`: «ningún texto incluye dígitos de estado, rutas de normalizador ni «Error:»».

No hay contacto de soporte (§6).

### 5.3 Los bloques try/catch y try/except están acotados a operaciones específicas, no envuelven funciones enteras

- **Ya en `main`:**
  - `incident_analyzer/analyze.py:36-44`;
  - `nexova_shared/incident_csv/reader.py:50-53`;
  - `modules/incident_manager/router.py:56-58`;
  - el `send()` del backoffice en `lib/api-client.ts`.
- **Rama, backend:**
  - `app/core/storage.py:62-67` (apertura) y `read`, `write` y `close`, cada uno con su `try` de una sola operación;
  - `app/auth/email.py:75-87`.
- **Rama, scripts:**
  - `scripts/seed_incidents.py:131-138`, solo la llamada a `seed()`;
  - `app/seed.py:191-196` y `:197-207`, dos `try` separados;
  - `app/auth/create_admin.py:45-50`, `:53-60` y `:72-79`.
- **Rama, frontends:**
  - backoffice `lib/api-client.ts:178-186` (`blob`);
  - tracker `lib/api-client.ts:287-292` (`readJson`).
- **Tests:**
  - `test_storage.py` → `ValidationIsNotAStorageErrorTests`, que comprueba que el 422, el 400 y la transición inválida dentro del `with` no se convierten en 503, y que un `ValidationError` sigue siendo un 500 opaco;
  - una mutación con la captura «ingenua» alrededor del `yield` hace fallar 2 tests.

### 5.4 Los bloques finally se usan correctamente para limpiar el estado de carga

**Backoffice.** Cada hook despacha el éxito o el error, y es esa acción la que cierra la carga. Su `finally` libera el `AbortController`:

| Hook | `finally` |
|---|---|
| `use-incident-analysis` | :228, :260 |
| `use-supplier-directory` | :225, :248, :298 |
| `use-incident-board` | :197, :244 |
| `use-incident-summary` | :86 |
| `use-incident-form` | :102 |
| `use-auth-form` | :82 |
| `use-profile` | :105, :139 |
| `use-auth-session` | :170 |

El único camino que no despacha nada es el abort, y solo ocurre en dos casos:
- **Un intento más nuevo:** ese intento vuelve a poner la carga y la termina él.
- **El desmontaje:** ya no hay vista que limpiar.

El temporizador del cliente se limpia en el `finally` de `send` (`lib/api-client.ts:260`), y su timeout garantiza que toda petición termina.

**Tracker:**

| Hook o componente | Mecanismo |
|---|---|
| `use-notes` | `finally` en :84-85 y :108-109 |
| `use-profile` · guardar | `finally` en :72-74 |
| `use-auth-form` | `.finally` en :55-57 |
| `candidate-form.tsx` | `finally` en :164-165 |
| `candidate-status-controls` | `useTransition`: React cierra `isPending` en todos los caminos |
| `use-records`, `use-record-detail`, `use-notes` · cargar, `use-profile` · cargar | sin `finally`: `then` y `catch` ponen los dos el estado final, y un `requestId` descarta las respuestas obsoletas |

En el tracker hay un arreglo de esta rama (T3) que lo hace correcto: el timeout cubre ahora la lectura del cuerpo (`lib/api-client.ts:278-280`), así que toda petición termina en éxito o error.

**Tests:**
- tracker `errors.test.mjs`: «un cuerpo que no termina de llegar acaba en TimeoutError (el timeout cubre response.json())»;
- backoffice `use-incident-analysis` y `use-supplier-directory`: carreras y desmontaje.

### 5.5 El optional chaining y los fallbacks se aplican donde corresponde para evitar errores de renderizado por valores undefined

Revisé todos los valores anulables según los tipos que producen los normalizadores. Todos tenían ya fallback, así que no se añadió ningún `?.` ni `??`.

**Backoffice:**

| Valor anulable (tipo) | Dónde se muestra | Cómo se muestra |
|---|---|---|
| `percentage` (`types/incidents.ts:28`) | `incidents/distribution-table.tsx:45` | `=== null ? '—' : …%` |
| `average_score` (`types/incidents.ts:47`) | `incidents/satisfaction-panel.tsx:17` | `?? '—'` |
| `ApiErrorBody.code` y `.detail` (`types/incidents.ts:76-77`) | no se muestran; `invalid_csv` usa `detail ?? ''` | `analysis-error.tsx:69` comprueba `!== ''` |
| `contract_renewal_date` (`types/suppliers.ts:45`) | `suppliers/supplier-badges.tsx:31` y `lib/supplier-renewal.ts:31` | `—` o `{kind:'none'}` |
| `contact_email` y `notes` (`types/suppliers.ts:46-47`) | `suppliers/supplier-table.tsx:82-83` | se omiten si son `null` |
| `field: … \| null` (suppliers, incident-manager y auth) | `*-error.tsx` | mensaje general y `?? 'general'` en la `key` |
| `profile` y sus campos (`types/auth.ts:19-31`) | `auth/profile-view.tsx:16-18, 59-78` | `profile?.x ?? ''` y `display()` → `—` |

**Tracker:**

| Valor anulable (tipo) | Dónde se muestra | Cómo se muestra |
|---|---|---|
| `linkedin_url` y `cv_url` (`types/record.ts:28-29`) | `candidate-detail.tsx`, en `LinkOrText` | enlace http(s), texto o «Sin especificar» |
| los mismos en el formulario | `candidate-form.tsx:54-55` | `?? ''` |
| `profile` y sus campos (`types/auth.ts:19-31`) | `auth/profile-view.tsx:15, 56-75` | `profile?.x ?? ''` y `display()` → `—` |
| `AuthFormErrors.form` (`types/auth.ts:83`) | `FormErrorMessage` | no se pinta si es `null` |
| `error` y `addNoteError` (hooks) | `candidate-list`, `candidate-detail`, `notes-list` y `note-form` | `error ? … : ''` |
| `record` (`use-record-detail`) | `candidate-detail.tsx` | `if (!record) return null` |

### 5.6 Las rutas del backend devuelven respuestas de error estructuradas y limpias con los códigos HTTP correctos

- **Ya en `main`:**
  - el formato `{detail, code}` y los handlers de `app/core/errors.py:169-190`;
  - el 422 sin `input`, `ctx` ni `url`;
  - el 400 propio del gestor de incidencias (SPECS Parte E);
  - el 500 opaco (`:193-224`).
- **Rama:** el 503 `storage_unavailable` (`app/core/errors.py:151-160`), documentado en `services/api/SPECS.md` §4, §5, §12, §18, §31 y §33 y en el README.
- **Tests:**
  - `test_errors.py` y `test_incident_manager_api.py` (ya en `main`);
  - `test_storage.py`: `test_corrupt_suppliers_file`, `test_corrupt_incidents_file`, `test_corrupt_auth_file`, `test_database_path_that_cannot_be_opened` y `test_write_failure`.

### 5.7 Ninguna información sensible aparece en la salida de errores entregada al cliente

- **Ya en `main`:**
  - el middleware del 500 registra solo la clase (`app/core/errors.py:220-221`);
  - `test_privacy.py`;
  - `production-source` del backoffice prohíbe `console.*` y `cause`.
- **Rama, backend:**
  - `log_storage_failure` (`app/core/errors.py:237-244`) registra solo el almacén y la clase;
  - el 503 no lleva ruta ni contenido y se lanza sin la excepción original.
- **Rama, frontends:**
  - los límites de error no leen el error;
  - el tracker ya no muestra los mensajes de los normalizadores ni el código HTTP.
- **Tests:**
  - `test_storage.py`: `assertUnavailable`, que comprueba que no salen la ruta ni un email ficticio, y `test_the_503_does_not_carry_the_original_exception`;
  - `test_password_reset.py`: `test_truncated_provider_response_is_logged_as_a_delivery_failure`;
  - backoffice `production-source`: «existen los límites de error… sin consola ni datos del error»;
  - tracker `production-source`: «nada en components/ ni en app/ muestra error.message, .digest ni hace console.*»;
  - tracker `errors.test.mjs`: «el mensaje descriptivo de un normalizador nunca llega al usuario».

### 5.8 Los scripts de Python gestionan errores de I/O y terminan con códigos de salida apropiados en caso de fallo

- **Ya en `main`:** `scripts/analyze.py:89-94` y `:102-104` (código 1); `seed_incidents.py:111-126` (códigos 1 y 2).
- **Rama:**
  - `seed_incidents.py:131-138`: base ilegible o corrupta → 2;
  - `app/seed.py:191-207`: `ConfigError` o base → 1;
  - `app/auth/create_admin.py:45-79`: configuración, cancelación o base → 1, sin crear nada ni mostrar la contraseña;
  - `analyze.py:64-75`: `describe_os_error` y Ctrl+C.
- **Tests:**
  - `test_incident_manager_seed.py`: `StorageErrorTests`, que comprueba código 2, sin «Traceback» y sin la ruta, y `test_read_error_without_strerror_shows_the_class_name`;
  - `test_suppliers_seed.py`: `SeedMainErrorTests`;
  - `test_create_admin.py`: `CreateAdminErrorTests`;
  - `packages/incident-analyzer/tests/test_cli_errors.py`.

## 6. Lo que no se hizo y por qué

| Tema | Motivo |
|---|---|
| **B5**, contacto de soporte en los mensajes de error | El contexto de Nexova no define ningún contacto de soporte y no se inventa ([`.agents/rules/nexova-context.md`](../.agents/rules/nexova-context.md)). Los errores ofrecen «Reintentar» y un enlace a inicio, las otras dos salidas que admite el ticket |
| **T5**, señal de cancelación externa en `request()` del tracker | Se acerca más a un refactor que a gestión de errores. Las respuestas obsoletas ya se descartan, y desde T3 toda petición termina |
| **`BrokenPipeError`** en `analyze.py` (redirigir la salida a `head`) | En Windows, escribir en una tubería cerrada da `OSError` con `EINVAL`, no `BrokenPipeError`: no hay un test fiable y pequeño |
| **Riesgo de duplicación del seed** del gestor | `IncidentRepository.seed` hace dos escrituras no atómicas (incidencias y después `seed_keys`). Si falla la segunda, la siguiente ejecución duplica. Es consistencia de datos, no gestión de errores; queda en «Decisiones y problemas conocidos» de `progress.md`. Por eso el mensaje de S1 no promete «no se ha insertado nada» |
| **La consola del navegador en los límites de error** | React registra en la consola, con su mensaje y su traza, los errores que capturan `error.tsx` y `global-error.tsx`; el código propio no los registra ni los muestra. La regla para que no expongan datos (ningún error lanzado en producción lleva datos de la API o del usuario en su mensaje) está en [`uis/backoffice/CLAUDE.md`](../uis/backoffice/CLAUDE.md) |

## 7. Validación

### 7.1 `main` (`6dfa013`) frente a `HEAD`

| Subproyecto | `main` | `HEAD` |
|---|---|---|
| `services/api` | 289 OK | **312 OK** |
| `packages/incident-analyzer` | 118 OK (7 omitidos) | **121 OK** (7 omitidos) |
| `packages/shared` | 81 OK | 81 OK |
| `src/` (`npm run check`) | 97 OK | 97 OK |
| backoffice `tsc` / `lint` | limpio / limpio | limpio / limpio |
| backoffice tests | 332 | **344** |
| backoffice `build` | OK, 12 rutas | OK, 12 rutas |
| tracker `tsc` | limpio | limpio |
| tracker `lint` | 4 errores `set-state-in-effect` | los mismos 4, ninguno nuevo |
| tracker tests | 35 | **55** |
| tracker `build` | OK, 9 rutas | OK, 9 rutas |

**Cómo se midió `main`:** en un worktree temporal de `6dfa013`.
- `tsc` de las apps necesita antes, en un checkout nuevo, los tipos que Next genera en `.next/types`.
- El `build` de `main` no puede correr con `node_modules` enlazado (Turbopack rechaza un enlace que apunta fuera del proyecto). La columna `main` usa el build del propio repo con el código de cada app idéntico a `main`; `git diff --quiet` lo confirma.

**Además:**
- `git diff main..HEAD --stat` es idéntico con y sin `--ignore-cr-at-eol`.
- La rama no incluye `.vscode/`, `.env`, `*.tsbuildinfo`, `.next/` ni bases de datos.
- No cambia ningún `package.json`, `pyproject.toml` ni lockfile.

### 7.2 Comandos (Windows PowerShell)

Desde la raíz del monorepo. El venv de la API se instala como indica [`services/api/README.md`](../services/api/README.md), con los tres paquetes editables.

```powershell
services\api\.venv\Scripts\python -m unittest discover -s services/api/tests -t services/api
python -m unittest discover -s packages/incident-analyzer/tests -t packages/incident-analyzer
python -m unittest discover -s packages/shared/tests -t packages/shared
npm run check
```

Lo mismo en cada app (`uis\backoffice` y `uis\talent-pipeline-tracker`):

```powershell
cd uis\backoffice
npx tsc --noEmit
npm run lint
npm run build
node --disable-warning=MODULE_TYPELESS_PACKAGE_JSON --import ./tests/support/resolve-alias.mjs --test --test-timeout=10000 "tests/*.test.mjs"
```

En el tracker, `npm run lint` debe dar exactamente los 4 errores anteriores (`use-notes`, `use-record-detail` y `use-records`).

### 7.3 Entorno para la verificación manual

- **Bases de datos:** siempre bases temporales, nunca `services/api/data/`. Se fijan en la sesión de PowerShell **antes** de arrancar la API:

```powershell
$env:SUPPLIERS_DB_PATH = "$env:TEMP\nexova-audit\suppliers.json"
$env:AUTH_DB_PATH = "$env:TEMP\nexova-audit\auth.json"
$env:INCIDENTS_DB_PATH = "$env:TEMP\nexova-audit\incidents.json"
```

- **Arranque de la API, el backoffice y el tracker** (puertos, `CORS_ALLOWED_ORIGINS`, `NEXT_PUBLIC_API_URL` y `NEXT_PUBLIC_AUTH_API_URL`): ver [`docs/local-development.md`](./local-development.md).

### 7.4 Casos de error

Los resultados de la columna derecha se comprobaron en esta rama.

**API y scripts:**

| Caso | Cómo provocarlo | Resultado esperado |
|---|---|---|
| Base corrupta (API) | Escribir `{"suppliers": {` en el `suppliers.json` temporal → `GET /suppliers` con token | 503 `{"detail":"storage is temporarily unavailable","code":"storage_unavailable"}`; en el log, `storage suppliers is unavailable: JSONDecodeError`, sin ruta |
| `auth.json` corrupto (API) | Igual con `auth.json` → `POST /auth/login` | 503; restaurado el archivo, el login vuelve a responder |
| Seed con base dañada | `services\api\.venv\Scripts\python scripts\seed_incidents.py packages\incident-analyzer\tests\fixtures\incidents-acceptance-synthetic.csv --db $env:TEMP` | Código 2; stderr con `storage incidents is unavailable: PermissionError` y `error: cannot open or write the incidents database (…)`, sin traceback |
| `uv run seed` con email a medias | `$env:RESEND_API_KEY = "x"` y después `uv run seed` en `services\api` | Código 1; «Error de configuración: RESEND_API_KEY, EMAIL_FROM and PASSWORD_RESET_URL must be set together…» |
| `create-admin` cancelado | `uv run create-admin` en `services\api`, y Ctrl+C en la contraseña | Código 1; «Operación cancelada. No se ha creado ningún usuario.» |

**Backoffice:**

| Caso | Cómo provocarlo | Resultado esperado |
|---|---|---|
| Ruta inexistente | `/esta-ruta-no-existe` | «Página no encontrada», con enlace a inicio |
| API parada | Parar la API y navegar a `/suppliers`, `/incident-manager` e `/incidents` (analizar un CSV) sin recargar | «No se pudo conectar con el servidor. Comprueba tu conexión e inténtalo de nuevo. Si el problema continúa, avisa al equipo técnico.», con «Reintentar» |
| `auth.json` corrupto | Recargar cualquier vista protegida | Guard: «No se pudo comprobar la sesión / El servidor tuvo un problema…», con «Reintentar» y «Cerrar sesión». Al reintentar se ve «Reintentando…» con spinner |

**Tracker:**

| Caso | Cómo provocarlo | Resultado esperado |
|---|---|---|
| Rutas inexistentes | `/esta-ruta-no-existe` y `/candidates/id-que-no-existe` | El not-found raíz, y el de la candidatura |
| 500, red caída o cuerpo colgado | Simulado en la consola del navegador (ver abajo), en el listado, el detalle y las notas | Un texto fijo por tipo, con «Reintentar», sin ningún código; el cuerpo colgado termina a los 20 s con «El servidor tardó demasiado…» |
| POST 2xx con JSON roto | Simulado: «Nueva candidatura» → enviar | «Se guardó, pero no se pudo leer la respuesta; recarga el listado.» y el botón de enviar deshabilitado; al cerrar y reabrir, el formulario está vacío |
| `auth.json` corrupto | Recargar | Texto del guard por tipo y «Reintentar» con carga |

**Simulador de fallos de la API de candidaturas.** Se pega en la consola del navegador con el tracker abierto y solo afecta a esa pestaña. Navega después con los enlaces de la app, sin recargar, para conservarlo. Nunca escribe en la API de candidaturas: los POST los responde el simulador.

```js
window.__realFetch = window.fetch;
window.__qa = { records: 'pass', detail: 'pass', notes: 'pass' }; // 'pass' | '500' | 'network' | 'hang'
window.fetch = async (input, init = {}) => {
  const url = String(input instanceof Request ? input.url : input); // Next también pasa objetos URL
  if (!url.includes('/tracker/api/v1')) return window.__realFetch(input, init);
  const method = String(init.method || 'GET').toUpperCase();
  if (method !== 'GET') return new Response('{"id": "qa", "full_na', { status: 201, headers: { 'content-type': 'application/json' } });
  const route = /\/notes/.test(url) ? 'notes' : /\/records\/[^/?]+/.test(url) ? 'detail' : 'records';
  const mode = window.__qa[route];
  if (mode === '500') return new Response('{"detail":"x"}', { status: 500, headers: { 'content-type': 'application/json' } });
  if (mode === 'network') throw new TypeError('Failed to fetch');
  if (mode === 'hang') return new Response(new ReadableStream({ start(c) { init.signal?.addEventListener('abort', () => c.error(new DOMException('aborted', 'AbortError'))); } }), { status: 200, headers: { 'content-type': 'application/json' } });
  return window.__realFetch(input, init);
};
```

**Web:** sirve `uis/website` con un servidor estático que devuelva `404.html` en las rutas inexistentes, como Netlify, y abre `/a/b/c/no-existe`. Debe verse la página con su logo y su navegación, y a 375 px no debe haber scroll horizontal (`scrollWidth` = 375).

### 7.5 Smoke test de los caminos normales

Comprueba que los caminos sin error siguen funcionando. **Durante la auditoría solo se recorrieron en el navegador** el login de las dos apps (con usuarios de prueba creados por la API) y la lectura del listado y de un detalle del tracker. El resto lo cubren los tests automáticos de cada app y está pendiente de recorrer a mano:

1. **`/incidents`:** analizar `packages/incident-analyzer/tests/fixtures/incidents-synthetic.csv` y descargar la exportación (`results.csv`).
2. **`/suppliers`:** dar de alta un proveedor, cambiar su tarifa y suspenderlo.
3. **`/incident-manager/new`:** registrar una incidencia. Después, en `/incident-manager`, cambiarla de estado y comprobar que el resumen se actualiza.
4. **Tracker:** crear una candidatura, editarla, cambiar su estado o etapa, y añadir y borrar una nota.
   - **Ojo:** esto escribe en la API de candidaturas configurada en `NEXT_PUBLIC_API_URL`; úsala solo si se puede escribir en ella.
   - Comprueba también que «Nueva candidatura» se abre vacía tras crear una.

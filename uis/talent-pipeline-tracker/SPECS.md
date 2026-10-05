# Especificación Técnica (SPECS.md): Talent Pipeline Tracker

> **AVISO IMPORTANTE DE MODO DE EJECUCIÓN:**
>
> Este documento es **exclusivamente una especificación técnica de arquitectura y diseño de software**.
>
> **NO debes ejecutar, implementar ni escribir el código del proyecto en esta interacción.**
>
> El desarrollo de esta interfaz se llevará a cabo de forma progresiva mediante el **Método del Pintor** (*Painter Methodology*), capa a capa, mediante prompts específicos. El objetivo de esta especificación es definir, validar y mantener las pautas, restricciones y estructura del proyecto antes de su implementación.

---

## 0. Verificación previa obligatoria (Capa 0)

El contrato OpenAPI deja cuatro respuestas sin schema (`{}`) y no describe ciertos comportamientos del servidor. Estas incógnitas **deben resolverse empíricamente antes de escribir la Capa 1**, porque condicionan tipos, arquitectura de carpetas y requisitos funcionales.

| # | Incógnita | Cómo verificarla | Estado | Bloquea a |
|---|---|---|---|---|
| V-1 | Forma de la respuesta de `GET /records` (¿array plano o envoltorio con metadatos de paginación?) | `GET /records?limit=1` | ✅ **RESUELTO** 2026-08-26 → §4.8.1 | §4.8, REQ-2 |
| V-2 | Forma de la nota devuelta por `GET /records/{id}/notes` y `POST /records/{id}/notes` (¿qué campo contiene el `note_id`?) | Crear un registro desechable, añadirle una nota y leer la lista | ✅ **RESUELTO** 2026-08-26 → §4.8.3 | §4.8, REQ-3 |
| V-3 | ¿`PUT /records/{id}` conserva o resetea `status` y `stage`? (`RecordCreate` no los incluye) | Sobre un registro desechable: `PATCH` a `selected`/`offer_presented`, luego `PUT` y releer | ✅ **RESUELTO** 2026-08-26 — **los conserva**; `PUT` no puede modificarlos → §5.2 | REQ-4 |
| V-4 | ¿La API permite el consumo desde el origen de la aplicación? | `curl` con cabecera `Origin` explícita + preflight `OPTIONS` | ✅ **RESUELTO** 2026-08-26 — **permitido, sin proxy** → §5.1 | §2.3, §3, §5.1 |
| V-5 | Forma de la respuesta de `GET /records/{id}` y código devuelto ante un `id` inexistente | `GET /records/{id-inventado}` | ✅ **RESUELTO** 2026-08-26 — devuelve **404** → §4.8.2, §5.4 | REQ-1, §5.4 |

**Regla:** el resultado de cada verificación se documenta en la sección correspondiente marcado como **CONTRATO OBSERVADO**, con fecha y método de comprobación. Un contrato observado es válido para tipar, pero es **más frágil** que el contrato OpenAPI y debe revalidarse si la API cambia.

Mientras una verificación esté pendiente, su sección permanece marcada como `⚠️ PENDIENTE (V-n)` y **no se implementa código que dependa de ella**.

---

## 1. Visión General del Proyecto

**Talent Pipeline Tracker** es un panel de gestión de candidaturas diseñado para visualizar, filtrar, registrar y gestionar el flujo de selección de candidatos mediante la API REST disponible bajo el prefijo `/tracker/api/v1`.

El proyecto está inicializado en la ruta relativa `/uis/talent-pipeline-tracker/` utilizando el stack oficial de **Next.js (App Router)**, **TypeScript** y **Tailwind CSS**.

La interfaz debe respetar estrictamente el contrato OpenAPI 3.1.0 proporcionado por la API.

**Regla principal para la implementación:** no inventar campos, modelos, endpoints, parámetros ni estructuras de respuesta que no estén definidos en el contrato OpenAPI **ni verificados empíricamente según el protocolo de la §0**.

Cuando una respuesta de la API no tenga schema definido y no haya sido verificada, no asumir su estructura ni crear modelos ficticios.

---

## 2. Pautas y Principios de Desarrollo

### 2.1 Método del Pintor (Painter Methodology)

El desarrollo se ejecutará progresivamente por capas:

0. **Verificación:** resolución de las incógnitas V-1 a V-5 de la §0 y actualización de este documento.
1. **Boceto / Estructura:** definición de tipos TypeScript basados en OpenAPI, cliente API, normalizadores y componentes base.
2. **Color / Componentes visuales:** construcción de una UI accesible, responsive y con estados visuales claros.
3. **Detalles / Interacciones:** gestión de estado síncrono/asíncrono, mutaciones, feedback visual y gestión de notas.
4. **Acabado / Refinamiento:** manejo de errores, accesibilidad y revisión WCAG 2.2 nivel AA.

### 2.2 Stack Tecnológico Estricto

* **Framework:** Next.js con App Router.
* **Lenguaje:** TypeScript en modo estricto, sin `any`.
* **Estilos:** Tailwind CSS **v4** (configuración vía CSS con `@import "tailwindcss"`; **no** existe `tailwind.config.ts`).
  * *Si el proyecto ya está inicializado con Tailwind v3, corregir esta línea y mantener `tailwind.config.ts` en el árbol. La versión debe quedar fijada explícitamente aquí, nunca implícita.*
* **Gestión de estado:** únicamente hooks estándar de React, incluyendo `useState`, `useContext`, `useReducer`, `useOptimistic` y hooks personalizados.

**Prohibido:** Redux, Zustand, Recoil, Jotai u otras librerías externas de gestión de estado.

No añadir dependencias externas salvo que una instrucción posterior lo autorice expresamente.

### 2.3 Estrategia de renderizado (decisión explícita)

App Router usa Server Components por defecto, pero el diseño de este proyecto (hooks personalizados, `useOptimistic`, mutaciones con feedback inmediato) es de cliente. Para evitar ambigüedad en los prompts de implementación:

* Las páginas de listado y detalle son **Client Components** (`'use client'`).
* La obtención de datos se realiza **en el navegador**, desde hooks que invocan a `services/`.
* **No** se usan Server Actions ni fetch en servidor en esta versión.
* **CORS verificado (V-4):** el consumo directo desde el navegador está autorizado. **No se implementa proxy** ni Route Handlers.

### 2.4 Arquitectura Orientada a Accesibilidad

La interfaz debe priorizar una experiencia accesible, con **WCAG 2.2 nivel AA** como criterio de revisión:

* Navegación completa por teclado cuando corresponda: `Tab`, `Shift+Tab`, `Enter`, `Escape` y teclas de flecha.
* Uso de HTML semántico: `<main>`, `<section>`, `<article>`, `<header>`, `<nav>`, `<form>`, `<label>`, `<button>`, `<table>`, etc.
* Uso de ARIA únicamente cuando sea necesario: `aria-expanded`, `aria-live`, `aria-controls`, `aria-invalid`, `role="status"`, etc.
* Gestión correcta del foco en modales, diálogos y paneles interactivos.
* Contraste suficiente y feedback que no dependa únicamente del color.
* Mensajes de carga, error y éxito accesibles.

### 2.5 Diseño Responsive y UI

* Enfoque **Mobile-First**.
* Adaptación a móviles, tablets y escritorios.
* Priorizar la **funcionalidad sobre el ornamento estético**.
* Interfaz sobria, clara y centrada en la eficiencia operativa.
* Los datos deben seguir siendo utilizables en pantallas pequeñas. Se pueden utilizar tarjetas o representaciones alternativas cuando una tabla no resulte adecuada.

---

## 3. Estructura Flexible del Proyecto

> **Nota:** la siguiente estructura es orientativa y puede evolucionar durante el desarrollo siempre que se mantenga una separación razonable de responsabilidades y se respeten las restricciones de este documento.

```text
/uis/talent-pipeline-tracker/

├── app/
│   ├── favicon.ico
│   ├── globals.css
│   ├── layout.tsx
│   │
│   ├── page.tsx
│   │
│   └── candidates/
│       └── [id]/
│           ├── page.tsx
│           └── not-found.tsx
│
├── components/
│   │
│   ├── candidates/
│   │   ├── candidate-list.tsx
│   │   ├── candidate-table.tsx
│   │   ├── candidate-card.tsx
│   │   ├── candidate-detail.tsx
│   │   ├── candidate-form.tsx
│   │   ├── candidate-filters.tsx
│   │   ├── candidate-pagination.tsx
│   │   └── candidate-status-controls.tsx
│   │
│   ├── notes/
│   │   ├── notes-list.tsx
│   │   ├── note-form.tsx
│   │   └── note-item.tsx
│   │
│   └── ui/
│       ├── badge.tsx
│       ├── button.tsx
│       ├── input.tsx
│       ├── select.tsx
│       ├── loading-spinner.tsx
│       └── toast-notification.tsx
│
├── hooks/
│   ├── use-records.ts
│   ├── use-record-detail.ts
│   ├── use-notes.ts
│   └── use-debounce.ts
│
├── services/
│   ├── records.service.ts
│   ├── notes.service.ts
│   └── normalizers.ts           # unknown -> tipos firmes (frontera de confianza)
│
├── lib/
│   ├── api-client.ts
│   └── format.ts                # formateo defensivo de fechas y valores
│
├── types/
│   ├── record.ts
│   └── api.ts
│
├── .env.local
└── package.json
```

La nomenclatura `candidate` puede utilizarse para componentes de presentación. Los modelos y DTOs que representen directamente la API deben mantener los nombres del contrato: `RecordOut`, `RecordCreate`, `RecordPatch` y `NoteCreate`.

### 3.1 Frontera de confianza

`services/normalizers.ts` es el **único lugar** del proyecto donde puede existir el tipo `unknown` procedente de la red. Su responsabilidad es validar la forma real de la respuesta y devolver tipos firmes.

```typescript
// services/records.service.ts
async function fetchRecords(params: RecordQueryParams): Promise<RecordsPage> {
  const data: unknown = await apiClient.get('/records', params);
  return normalizeRecordsPage(data); // valida y estrecha desde unknown
}
```

Consecuencias:

* Hooks y componentes **nunca** manipulan `unknown` ni hacen aserciones de tipo.
* Si el backend cambia su forma de respuesta, el fallo se localiza en un solo archivo.
* Un normalizador que recibe una forma inesperada debe lanzar un error descriptivo, no devolver datos parciales silenciosamente.

### 3.2 Variables de entorno

```text
# .env.local
NEXT_PUBLIC_API_URL=https://playground.4geeks.com/tracker/api/v1
```

* La URL base **nunca** se escribe literal en el código; se lee siempre desde esta variable en `lib/api-client.ts`.
* `api-client.ts` debe fallar con un error explícito en arranque si la variable no está definida.

---

## 4. Definición de Modelos y Tipos (TypeScript basado en OpenAPI 3.1.0)

Los siguientes tipos deben corresponder exactamente a los schemas definidos en `/tracker/api/v1/openapi.json`.

### 4.1 Estados y etapas

El OpenAPI declara `status` y `stage` como `string`, **no** como `enum`. Los valores conocidos aparecen únicamente en la descripción de los parámetros de consulta.

Para ser fiel al contrato sin renunciar a la ayuda del compilador:

```typescript
export type KnownStatus =
  | 'received'
  | 'in_progress'
  | 'selected'
  | 'discarded';

export type KnownStage =
  | 'pending'
  | 'review'
  | 'personal_interview'
  | 'technical_interview'
  | 'offer_presented';

// Acepta cualquier string (fiel al contrato) pero autocompleta los conocidos
export type RecordStatus = KnownStatus | (string & {});
export type RecordStage = KnownStage | (string & {});
```

Reglas derivadas:

* Los filtros y selectores de la UI se construyen a partir de `KnownStatus` / `KnownStage`.
* Todo `switch` o mapa que traduzca estado/etapa a etiqueta, color o icono **debe tener un caso por defecto**. Un valor desconocido devuelto por la API se muestra de forma neutra (el valor crudo), nunca provoca un fallo de renderizado.
* **No** convertir estos valores en un `enum` de TypeScript mientras el OpenAPI los declare como `string`.

### 4.2 `RecordOut`

```typescript
export interface RecordOut {
  id: string;
  full_name: string;
  email: string;
  phone: string;
  position: string;
  linkedin_url: string | null;
  cv_url: string | null;
  status: RecordStatus;
  stage: RecordStage;
  experience_years: number;
  notes_count: number;
  applied_at: string;
  updated_at: string;
}
```

Todos los campos son obligatorios según el schema `RecordOut`. `linkedin_url` y `cv_url` son obligatorios pero **nullables**: siempre están presentes, su valor puede ser `null`.

**Fechas:** `applied_at` y `updated_at` son `string` **sin `format: date-time` declarado**. En la práctica (observado 2026-08-26) llegan como ISO 8601 en UTC, p. ej. `2026-08-25T16:59:42.755489Z`, pero eso es comportamiento observado, no garantía contractual. El formateo se realiza siempre mediante `lib/format.ts` con comportamiento defensivo: si `new Date(valor)` produce `Invalid Date`, se muestra el string crudo, nunca `NaN` ni `Invalid Date`.

**Calidad de los datos:** esta es una API pública compartida cuyos registros crean otros usuarios. Los valores **no son fiables**:

* `linkedin_url` y `cv_url` pueden contener texto que no es una URL válida (observado: markdown crudo del tipo `[texto](url)`). **Nunca insertar estos campos directamente en un `href`** sin validar antes que son URLs http(s) reales; si no lo son, mostrar el texto plano sin enlazar.
* Los identificadores son UUID y los registros pueden ser modificados o eliminados por terceros en cualquier momento. No cachear datos entre sesiones asumiendo que siguen existiendo.

**`notes_count`:** es un contador calculado por el servidor. Queda **obsoleto en memoria** tras crear o eliminar una nota. Ver REQ-3 para la regla de reconciliación.

### 4.3 `RecordCreate`

Utilizado por `POST /records` y `PUT /records/{id}`:

```typescript
export interface RecordCreate {
  full_name: string;
  email: string;
  phone: string;
  position: string;
  linkedin_url?: string | null;
  cv_url?: string | null;
  experience_years: number;
}
```

Campos obligatorios:

* `full_name`
* `email` (`format: email`)
* `phone`
* `position`
* `experience_years` (`number`, admite decimales)

Campos opcionales:

* `linkedin_url`
* `cv_url`

`RecordCreate` **no incluye** `status` ni `stage`. El servidor asigna los valores iniciales.

### 4.4 `RecordPatch`

Utilizado por `PATCH /records/{id}`:

```typescript
export interface RecordPatch {
  status?: RecordStatus | null;
  stage?: RecordStage | null;
}
```

El `PATCH` actual **solo permite modificar `status` y `stage`**.

No utilizar `PATCH` para modificar:

* `full_name`
* `email`
* `phone`
* `position`
* `linkedin_url`
* `cv_url`
* `experience_years`

Para modificar esos datos utilizar `PUT /records/{id}` con un `RecordCreate` completo, respetando la regla de reconciliación de REQ-4.

### 4.5 `NoteCreate`

```typescript
export interface NoteCreate {
  content: string; // minLength: 1
}
```

`content` es obligatorio y no puede estar vacío. La validación de longitud mínima se replica en cliente antes de enviar.

El OpenAPI **no define un modelo `Note` de respuesta**. Ver §4.8.

### 4.6 Parámetros de consulta

```typescript
export interface RecordQueryParams {
  status?: string;
  stage?: string;
  search?: string;
  page?: number;
  limit?: number;
}
```

Restricciones declaradas en el OpenAPI:

* `page`: entero, mínimo `1`, default `1`.
* `limit`: entero, mínimo `1`, default `20`.
* `limit` **no tiene máximo declarado**. La UI debe imponer un tope propio razonable para no degradar el rendimiento.
* `search`: búsqueda en `full_name` o `email`.
* Los parámetros vacíos o sin valor **no se envían** en la query string.

### 4.7 Errores de validación

```typescript
export interface ValidationError {
  loc: Array<string | number>;
  msg: string;
  type: string;
}

export interface HTTPValidationError {
  detail?: ValidationError[];
}
```

### 4.8 Respuestas sin schema en el contrato

El OpenAPI no define schema (`{}`) para las respuestas de:

* `GET /records`
* `GET /records/{id}`
* `GET /records/{id}/notes`
* `POST /records/{id}/notes`

Estas formas **no se inventaron**: se determinaron mediante las verificaciones V-1, V-2 y V-5 de la §0 y quedan documentadas a continuación como **contrato observado**, con la única excepción indicada en §4.8.2.

#### 4.8.1 `GET /records` — ✅ CONTRATO OBSERVADO (V-1)

> **Verificado el 2026-08-26** mediante `curl` sobre `GET /records`.
>
> La respuesta es un **envoltorio con metadatos de paginación**. El array de resultados se llama **`data`**, no `items`.
>
> **Desviación respecto al OpenAPI:** cada elemento incluye un campo **`notes`** con el array completo de notas, que **no está declarado en el schema `RecordOut`**. El contrato OpenAPI está desactualizado respecto a la API real.

```typescript
// CONTRATO OBSERVADO 2026-08-26 — no declarado en OpenAPI
export interface RecordsPage {
  total: number;
  page: number;
  limit: number;
  data: RecordListItem[];
}

// RecordOut (según OpenAPI) + campo `notes` observado en la respuesta real
export interface RecordListItem extends RecordOut {
  notes: Note[];
}
```

Notas de implementación:

* `limit` en la respuesta refleja el valor efectivo aplicado (devuelve el default `20` si no se envía).
* Las notas vienen incrustadas, por lo que **el listado no necesita llamadas adicionales** para conocerlas. Aun así, la UI de listado solo debe mostrar `notes_count`; el contenido de las notas pertenece a la vista de detalle.
* El campo `notes` es una desviación del contrato: si en el futuro desapareciera, `RecordListItem.notes` debe tratarse como posiblemente ausente. El normalizador es responsable de tolerar su ausencia devolviendo `[]`.

#### 4.8.2 `GET /records/{id}` — ✅ PARCIALMENTE OBSERVADO (V-5)

> **Verificado el 2026-08-26.**
>
> Ante un `id` inexistente o con formato inválido: **`404`** con mensaje `record not found`.
>
> **Pendiente menor:** confirmar si la respuesta `200` devuelve el `RecordOut` desnudo o incluye también el array `notes` incrustado, como hace `GET /records`. Dado el precedente de §4.8.4, no asumirlo: el normalizador del detalle debe tolerar la presencia **y** la ausencia de `notes`, devolviendo `[]` cuando no venga.

**Estructura del cuerpo del 404:** no verificada. FastAPI suele emitir `{"detail": "record not found"}`, pero **no debe asumirse**. El manejo del 404 se basa en el **código de estado**, nunca en el contenido del cuerpo.

#### 4.8.3 Notas — ✅ CONTRATO OBSERVADO (V-2)

> **Verificado el 2026-08-26** sobre los endpoints propios de notas.
>
> Identificador para `DELETE /records/{id}/notes/{note_id}`: campo **`id`** de la nota (UUID). El servidor lo genera automáticamente y añade `record_id` con el `id` del candidato recibido en la ruta.

```typescript
// CONTRATO OBSERVADO 2026-08-26
export interface Note {
  id: string;         // usado como {note_id} en el DELETE
  record_id: string;
  content: string;
  created_at: string; // ISO 8601 observado
}

// GET /records/{id}/notes
export interface NotesResponse {
  data: Note[];
  meta: { total: number };
}

// POST /records/{id}/notes -> devuelve la Note desnuda, SIN envoltorio
```

Notas de implementación:

* La nota **no tiene `updated_at`**: no existe edición de notas en esta API.
* El `POST` devuelve la nota creada con su `id`, por lo que puede añadirse al estado local sin refetch.
* `meta.total` es la fuente autorizada del número de notas y sirve para reconciliar `notes_count` (REQ-3).

#### 4.8.4 Inconsistencia de envoltorios ⚠️

La API **no usa un formato de envoltorio uniforme**. Formas observadas el 2026-08-26:

| Endpoint | Forma de la respuesta |
|---|---|
| `GET /records` | `{ total, page, limit, data }` — total al nivel raíz |
| `GET /records/{id}/notes` | `{ data, meta: { total } }` — total anidado, sin `page`/`limit` |
| `POST /records/{id}/notes` | Objeto `Note` desnudo, sin envoltorio |

**Consecuencia obligatoria:** cada endpoint tiene su **propio normalizador** en `services/normalizers.ts`. Está prohibido escribir un normalizador genérico de listas o asumir que un envoltorio observado en un endpoint aplica a otro. Los endpoints aún no verificados (V-5) pueden tener una cuarta forma.

---

## 5. Endpoints de la API (`/tracker/api/v1`)

### 5.1 URL base y origen

El OpenAPI declara el servidor como la ruta relativa `/tracker/api/v1`. La **URL absoluta real** es:

```text
https://playground.4geeks.com/tracker/api/v1
```

* La API **no declara `securitySchemes`**: no requiere autenticación, no se envían cabeceras `Authorization`.
* Todas las peticiones con cuerpo llevan `Content-Type: application/json`.

#### CORS — ✅ VERIFICADO 2026-08-26 (V-4)

**La API permite el consumo directo desde el navegador. No se requiere proxy.**

Petición simple con `Origin: http://localhost:3000`:

```text
Access-Control-Allow-Origin: *
Access-Control-Allow-Credentials: true
```

Preflight `OPTIONS` con `Access-Control-Request-Method: PATCH`:

```text
Access-Control-Allow-Origin: http://localhost:3000
Access-Control-Allow-Methods: DELETE, GET, HEAD, OPTIONS, PATCH, POST, PUT
Access-Control-Allow-Headers: content-type
Access-Control-Max-Age: 600
Vary: Origin
```

Conclusiones:

* Todos los métodos usados por la aplicación están autorizados, incluidos `PATCH`, `PUT` y `DELETE`.
* `content-type: application/json` está permitido, por lo que los `POST`/`PUT`/`PATCH` funcionan.
* El resultado del preflight se cachea 600 s.
* La aplicación consume la API **directamente desde el cliente**. `NEXT_PUBLIC_API_URL` apunta a la URL absoluta. **No se crea la carpeta `app/api/`.**

> ⚠️ **`Allow-Origin: *` combinado con `Allow-Credentials: true` es una configuración inválida** según la especificación CORS. Mientras no se envíen credenciales no causa problemas, pero el navegador **rechazará** cualquier petición que use `credentials: 'include'`, aunque el servidor responda correctamente.
>
> **Regla:** no establecer nunca la opción `credentials` en `fetch`. Esta API no tiene autenticación y no la necesita.

### 5.2 Records

**GET `/records`**

Obtiene registros. Query params opcionales: `status`, `stage`, `search`, `page`, `limit`.
Defaults: `page = 1`, `limit = 20`.
Respuesta `200`: **schema no definido** → ver §4.8.1.

**POST `/records`**

Body: `RecordCreate`.
Respuesta `201`: `RecordOut`.

**GET `/records/{id}`**

`id`: `string` (**no numérico** — no aplicar `parseInt`).
Respuesta `200`: **schema no definido** → ver §4.8.2.

**PUT `/records/{id}`**

Reemplaza los datos del registro.
Body: `RecordCreate`.
Respuesta `200`: `RecordOut`.

> ✅ **Verificado 2026-08-26 (V-3).** `PUT` **conserva** `status` y `stage`; tampoco permite modificarlos aunque se envíen. El cuerpo aceptado es exclusivamente `RecordCreate`. En la práctica, `PUT` reemplaza solo los datos personales y profesionales, y la posición del candidato en el pipeline es intocable desde este endpoint.
>
> Consecuencia: editar un candidato es una operación **segura**, no requiere paso de reconciliación posterior.

**PATCH `/records/{id}`**

Body: `RecordPatch`. Solo `status` y `stage`.
Respuesta `200`: `RecordOut`.

**DELETE `/records/{id}`**

Respuesta `204 No Content`, **sin cuerpo**.

### 5.3 Notes

**GET `/records/{id}/notes`** → `200`. Schema no declarado en OpenAPI; forma observada `{ data: Note[], meta: { total } }` (§4.8.3).

**POST `/records/{id}/notes`** → body `NoteCreate`, `201`. Devuelve la `Note` creada **sin envoltorio**, con `id` y `record_id` generados por el servidor (§4.8.3).

**DELETE `/records/{id}/notes/{note_id}`** → `note_id` es el campo `id` de la nota. Respuesta `204 No Content`.

### 5.4 Manejo de respuestas y errores

Reglas para `lib/api-client.ts`:

* **`204 No Content`:** comprobar el código **antes** de intentar parsear el cuerpo. Llamar a `.json()` sobre un 204 lanza una excepción.
* **`422`:** parsear como `HTTPValidationError` y mapear `detail[].loc` a los campos del formulario correspondiente para mostrar el error junto al input (`aria-invalid`).
* **`404`:** confirmado en `GET /records/{id}` con `id` inexistente o inválido (V-5). En el detalle de candidatura, delegar en `notFound()` de Next y renderizar `not-found.tsx`. La detección se basa en `response.status === 404`, **nunca** en el texto del cuerpo. No mostrar un error genérico.
* **Otros códigos 4xx/5xx:** error genérico con mensaje legible y opción de reintento.
* **Errores de red / `fetch` rechazado:** se distinguen de los errores HTTP y ofrecen reintento explícito.
* El cliente **no** silencia errores ni devuelve valores por defecto ante un fallo.

---

## 6. Requisitos Funcionales Detallados

### REQ-1: Vistas y navegación
- Crear una página de listado de candidaturas en `/`.
- Crear una página de detalle de candidatura en `/candidates/[id]`.
- El listado obtiene los datos mediante `GET /records`.
- El detalle obtiene los datos mediante `GET /records/{id}`.
- La navegación entre listado y detalle utiliza el sistema de rutas de Next.js, sin recargas completas de página.
- Un `id` inexistente debe resolverse mediante `not-found.tsx` (ver §5.4).

### REQ-2: Listado de candidaturas
- Mostrar como mínimo: nombre, puesto, estado actual y etapa actual.
- Implementar filtro por `status` y filtro por `stage`, con los valores de `KnownStatus` / `KnownStage`.
- Implementar búsqueda por nombre o email mediante `search`, con debounce aproximado de 300 ms.
- **Implementar controles de paginación** (anterior / siguiente e indicador de página) usando `page` y `limit`.
- **Al cambiar cualquier filtro o el término de búsqueda, `page` vuelve a `1`.**
- Si una respuesta descartada llega después de otra más reciente, debe ignorarse (control de condiciones de carrera en búsquedas con debounce).
- Mostrar estado de carga mientras se obtienen los datos y mensaje de error si la petición falla, con opción de reintento.
- Mostrar un estado vacío distinguible del estado de error ("sin resultados" ≠ "fallo al cargar").
- Mantener la interfaz usable en móvil mediante tabla, tarjetas o una representación responsive equivalente.

### REQ-3: Detalle de candidatura
- Mostrar los campos de `RecordOut`: nombre, email, teléfono, puesto, LinkedIn, CV, años de experiencia, estado, etapa, fecha de aplicación y fecha de actualización.
- `linkedin_url` y `cv_url` pueden ser `null` **o contener texto que no es una URL válida** (§4.2). Validar antes de renderizar: si no es una URL http(s), mostrar el texto plano o un marcador neutro, nunca un enlace roto.
- Las fechas se formatean con el comportamiento defensivo descrito en §4.2.
- Incluir controles para actualizar `status` y `stage` mediante `PATCH /records/{id}`.
- Mostrar las notas mediante `GET /records/{id}/notes`.
- Permitir añadir una nota mediante `POST /records/{id}/notes` (validando `minLength: 1` en cliente).
- Permitir eliminar una nota mediante `DELETE /records/{id}/notes/{note_id}`.
- **Reconciliación de `notes_count`:** tras crear o eliminar una nota, el contador mostrado se toma de `meta.total` de `GET /records/{id}/notes`, o de la longitud de la lista en memoria si no se refresca. Nunca del `notes_count` original de `RecordOut`, que queda obsoleto.
- No asumir propiedades de las notas que no estén confirmadas en §4.8.3.

### REQ-4: Gestión de candidaturas
- Formulario para registrar una nueva candidatura mediante `POST /records`.
- Formulario para editar datos de una candidatura mediante `PUT /records/{id}`.
- Ambos formularios validan en cliente los campos obligatorios de `RecordCreate` antes de enviar, incluyendo formato de email y `experience_years` numérico y no negativo.
- **Confirmado (V-3):** `PUT` conserva `status` y `stage`, por lo que la edición **no requiere** ningún paso de reconciliación ni advertencia al usuario. El formulario de edición se limita a los campos de `RecordCreate`; los controles de estado y etapa no aparecen en él, viven en el detalle y usan `PATCH`.
- Mostrar feedback de éxito o error tras cada operación.
- Los cambios rápidos de `status` y `stage` se realizan mediante `PATCH`; los cambios de datos personales o profesionales, mediante `PUT`.
- **Eliminación de registros:** `DELETE /records/{id}` existe en la API pero **queda deliberadamente fuera del alcance de esta versión**. Si se incorpora, requerirá confirmación explícita del usuario antes de ejecutarse.

### REQ-5: Estado y manejo asíncrono
- Todas las llamadas a la API se gestionan mediante `async/await`.
- Cada operación contempla estados de carga, éxito y error.
- Tras un `POST`, `PUT` o `PATCH`, actualizar la interfaz sin recargar la página completa.
- Evitar envíos duplicados mientras una mutación está en progreso (deshabilitar el control disparador).
- Tratar correctamente las respuestas `204 No Content` (§5.4).
- Si se emplea `useOptimistic`, debe existir una reversión explícita del estado optimista ante error, acompañada de mensaje al usuario.

### REQ-6: Estructura del código
- Separación clara entre: páginas/rutas, componentes, hooks, servicios API, cliente HTTP, normalizadores y tipos.
- Los componentes **no** realizan llamadas HTTP directamente.
- Las llamadas a la API se centralizan en `services/`.
- Los hooks gestionan estado y comportamiento de la interfaz.
- Los tipos TypeScript se mantienen alineados con el contrato OpenAPI y con los contratos observados de la §4.8.
- **No utilizar `any`.** `unknown` se permite exclusivamente en `services/normalizers.ts`.
- No introducir librerías externas de gestión de estado.
- No usar aserciones de tipo (`as`) para forzar respuestas de red; esa función corresponde a los normalizadores.

---

## 7. Regla de Fidelidad al Contrato API

Durante toda la implementación:

* **No inventar campos.**
* **No inventar modelos de respuesta.**
* **No inventar endpoints.**
* **No inventar estructuras de paginación** sin haberlas verificado según §0.
* **No añadir campos a `RecordCreate`.**
* **No añadir campos a `RecordPatch`.**
* **No utilizar `PATCH` para campos no definidos en `RecordPatch`.**
* **No convertir strings documentados en `enum` de TypeScript** si OpenAPI no los declara como `enum`.
* **No utilizar `any`;** `unknown` solo en la frontera de normalización.
* **No asumir estructuras de respuestas cuyo schema sea `{}`:** verificar, documentar como contrato observado y aislar en `services/`.
* **No escribir la URL base literal** fuera de la variable de entorno.

El contrato OpenAPI es la fuente de verdad para la integración con la API. Los contratos observados de la §4.8 son fuente de verdad **secundaria y revisable**, válida únicamente mientras la API no cambie.

Si una futura versión del OpenAPI modifica un modelo, endpoint o respuesta, los tipos y la implementación deberán adaptarse al nuevo contrato, y este documento se actualiza antes que el código.

---

## 8. Estado: Capa 0 cerrada

Las cinco verificaciones están resueltas. Resumen de lo aprendido frente al contrato OpenAPI:

| Hallazgo | Impacto |
|---|---|
| `GET /records` envuelve en `data`, no `items` | El tipado a ciegas habría producido una lista vacía sin error de compilación |
| `GET /records` incluye `notes` incrustadas, no declaradas en `RecordOut` | El OpenAPI está desactualizado respecto a la API real |
| Tres formas de envoltorio distintas entre endpoints | Normalizadores por endpoint, prohibido el genérico |
| Las notas no tienen `updated_at` | No existe edición de notas |
| `PUT` conserva `status`/`stage` | Editar un candidato es seguro; sin reconciliación |
| `404` en `id` inexistente | `not-found.tsx` en el detalle |
| CORS abierto para todos los métodos | Consumo directo, sin proxy |
| URLs de datos no fiables (markdown crudo en `cv_url`) | Validar antes de renderizar como enlace |

**La implementación puede comenzar por la Capa 1.**

---

## 9. Autenticación AUTH-02 (sesión contra `services/api` de Nexova)

Fuente: ticket AUTH-02 ([`docs/auth-frontend.md`](../../docs/auth-frontend.md)): todas las aplicaciones del monorepo salvo el website público exigen sesión. Contrato de autenticación: [`services/api/SPECS.md`](../../services/api/SPECS.md) Parte C (§18). Esta sección **no** cambia nada de las §1–§8: la API de candidaturas de 4Geeks sigue sin autenticación y **nunca** recibe el token (§5.1).

### 9.1 Dos APIs, dos variables

```text
# .env.local
NEXT_PUBLIC_API_URL=https://playground.4geeks.com/tracker/api/v1   # candidaturas (4Geeks), sin token
NEXT_PUBLIC_AUTH_API_URL=http://localhost:8000                     # services/api de Nexova (login, registro, perfil)
```

* Igual que §3.2: ninguna URL se escribe literal en el código y `lib/api-client.ts` falla al arrancar si falta cualquiera de las dos.
* `apiClient` (4Geeks) no envía `Authorization`. `authApiClient` (services/api) la envía en sus rutas protegidas (`GET /auth/me`, `PUT /profiles/me`); login (`POST /auth/login`, formulario OAuth2 con `username` = email) y registro (`POST /users`) son públicos.
* La app arranca en el puerto **3001** (`npm run dev`), un origen propio que `services/api` debe permitir en `CORS_ALLOWED_ORIGINS` (lo incluye su `.env.example`). Nunca se establece `credentials` en `fetch`.
* El puerto 3001 y `NEXT_PUBLIC_AUTH_API_URL` son configuración local propuesta en AUTH-02, **pendiente de revisión** (`docs/auth-frontend.md` §3.3), no parte del contrato de la API de candidaturas.

### 9.2 Vistas y protección

| Ruta | Acceso | Qué hace |
|---|---|---|
| `/login` | pública | `POST /auth/login`; si es correcto guarda el JWT en `localStorage` y va a `/`; si no, error claro y ningún token |
| `/register` | pública | `POST /users` (email, contraseña y `name`/`phone`/`address` opcionales; nunca `role`) y después `POST /auth/login`; errores 422/409 por campo |
| `/account/profile` | protegida | `GET /auth/me` (email + `Profile`) y `PUT /profiles/me` (nombre y contacto; campo vacío → `null`) |
| `/`, `/candidates/[id]` y cualquier ruta nueva | protegida | sin cambios funcionales |

* **Guard global** en el layout raíz (`components/auth/auth-guard.tsx`): toda ruta salvo `PUBLIC_PATHS` (`lib/auth-routes.ts`) exige sesión. La sesión se valida una vez por token con `GET /auth/me` (la única llamada protegida al cargar: los datos de candidaturas no usan el token); la vista no se muestra ni pide datos a 4Geeks hasta entonces.
* Sin token → `/login`. Un 401 de una ruta protegida de `services/api` → se borra el token y `/login`. Logout (cabecera) → se borra el token y `/login`.
* **Prohibido** el middleware/proxy de Next.js o una cookie para esta comprobación: el token vive en `localStorage`.

### 9.3 Código

* `lib/auth-token.ts` — único módulo que usa `localStorage` (solo el JWT).
* `lib/api-client.ts` — `authApiClient`: Bearer y tratamiento del 401 (`UnauthorizedError`) en un único sitio.
* `services/auth.service.ts` — login y registro comparten el paso de login; `describeAuthError` traduce errores a mensajes por campo.
* `services/normalizers.ts` — `normalizeAccessToken`, `normalizeCurrentUser`, `normalizeProfile` (frontera de confianza, §3.1).
* `hooks/use-auth-session.ts`, `use-auth-form.ts`, `use-profile.ts`; `components/auth/*`.
* Tests: `tests/auth.test.mjs` con el runner nativo de Node 24, sin dependencias (ver README, Validación).

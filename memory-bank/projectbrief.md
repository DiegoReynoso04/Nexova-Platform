# Project Brief — Nexova Solutions

> Fuente de verdad ampliada: `contexts/CONTEXT.md`. **Esa carpeta está en `.gitignore` (raíz, línea 8) y no viaja con el repositorio** — solo existe en checkouts locales que ya la tenían. Desde el 2026-09-27 (commit `6807f5e`) el **`README.md` raíz contiene ese mismo briefing** (contenido idéntico), así que el briefing general sí está versionado. Este archivo es el resumen derivado, más lo construido en el repo; los briefings por hito (`contexts/hitoN/*.md`) siguen siendo solo locales.

## La empresa

**Nexova Solutions** es una consultora de recursos humanos y adquisición de talento fundada en **2011**, con sede en **Valencia, España**, y una oficina de expansión en **Miami, Florida**. Tiene **120 empleados** y factura aproximadamente **8 millones de dólares anuales**. CEO: **Laura Mendoza**.

Tres líneas de negocio:

1. **Headhunting** ejecutivo y de mandos medios.
2. **Outsourcing** de equipos de soporte al cliente para empresas tecnológicas.
3. **Formación corporativa** en soft skills y liderazgo.

Clientes: medianas empresas de tecnología, retail y servicios financieros que externalizan gestión de talento.

## Por qué existe este repositorio

Nexova tiene reputación y red de contactos, pero **no tiene infraestructura para operar a escala**: procesos manuales, cero telemetría, decisiones con datos de una semana de antigüedad. Un equipo de AI Engineering (este repo) construye los sistemas, automatizaciones y herramientas inteligentes para que Nexova haga lo que ya hace bien, pero más rápido y con menos esfuerzo manual.

## Departamentos activos en este repo (hasta ahora)

| Departamento | Responsable | Qué se construyó | Dónde |
|---|---|---|---|
| Marketing y Comunicación | Carmen Ruiz | Sitio web corporativo (landing + formulario de registro de talento) — Hito 1 | `uis/website/` |
| Operaciones de Selección | Javier Almeida | Lógica de dominio: scoring y matching de candidatos — Hito 2 | `src/` (raíz) |
| Formación Corporativa (L&D) + Tecnología e Infraestructura | Elena Vargas (solicitante) / Sergio Molina (CTO) | Talent Pipeline Tracker — panel interno de gestión de candidaturas — Hito 3 | `uis/talent-pipeline-tracker/` |
| Atención al Cliente (outsourcing de soporte) | Roberto Díaz (Customer Support Lead) / Sergio Molina (CTO) | Procesador de reportes de incidentes: análisis del CSV exportado del helpdesk legado (validación, métricas por categoría/estado, índice de satisfacción, exportación) sin enviar datos a herramientas de IA externas — Fase 1 (núcleo + CLI), Fase 2 (API HTTP local; con autenticación JWT desde AUTH-01) y Fase 3 (vista web `/incidents` en el backoffice) | `packages/incident-analyzer/` + `scripts/analyze.py` + `services/api/` + `uis/backoffice/` (`/incidents`) |
| Recursos Humanos (interno), en coordinación con operaciones | Patricia Solís (HR Manager) / Sergio Molina (CTO, tech lead) | Directorio de proveedores: registro oficial y único de los servicios externos que contrata Nexova (sustituye la hoja de cálculo compartida por email). 15 proveedores iniciales, países Spain/USA, 9 categorías, estados `active`/`suspended`, trazabilidad de tarifas y renovaciones en 60 días. API FastAPI + TinyDB + Pydantic con seeder (`uv run seed`) y vista web `/suppliers` en el backoffice | `services/api/` (`/suppliers`) + `uis/backoffice/` (`/suppliers`) |
| Tecnología (CTO) + Atención al Cliente, con visibilidad para Dirección | Sergio Molina (CTO) / Roberto Díaz (Customer Support Lead) / Laura Mendoza (CEO) | **Gestor centralizado de incidencias (hecho; integrado en `main` con la PR #17, merge `6dfa013`, 2026-10-08):** registro estructurado de incidencias técnicas y operativas (no solo fallos de infraestructura: también quejas de clientes corporativos, errores de procesos de selección y problemas del soporte externalizado), con estados, orígenes, sedes y categorías propios, carga del histórico del CSV del helpdesk y panel de resumen. Hecho en seis fases (validación compartida, modelo y repositorio, seed del histórico, API `/api/incidents`, UI y documentación) en la rama `feature/centralized-incident-manager`; las decisiones de implementación (P4-1…P4-13) son del usuario y están pendientes de revisión por el tech lead o la CTO. Guía de revisión: `docs/centralized-incident-manager-review.md` | `packages/shared/` (F1), `services/api/` → `app/modules/incident_manager/` (F2 y F4), `scripts/seed_incidents.py` (F3), `uis/backoffice/` → `/incident-manager` (F5) |

Ver `contexts/hito1/CONTEXT-WEB-NEXOVA.md`, `contexts/hito2/CONTEXT-HITO2.md` y `contexts/hito3/CONTEXT-HITO3.md` para el briefing completo de cada encargo. El del procesador de incidentes es [`docs/COMPANY_INCIDENT_FILE_ANALIZER_PROJECT.md`](../docs/COMPANY_INCIDENT_FILE_ANALIZER_PROJECT.md) el del directorio de proveedores es [`docs/ligthweight-storage-api.md`](../docs/ligthweight-storage-api.md) y el del gestor centralizado de incidencias es [`docs/centralized-incident-manager.md`](../docs/centralized-incident-manager.md) — a diferencia de los anteriores, viven en `docs/`, no en `contexts/`.

## Departamentos descritos en `contexts/CONTEXT.md` sin herramienta propia todavía

- **Ventas y Desarrollo de Negocio** — Marcos Ibáñez / Megan Clarke.
- **Recursos Humanos (interno)** — Patricia Solís. Solo tiene el directorio de proveedores (tabla de arriba); el resto de sus necesidades (portal interno, onboarding, KPIs de RRHH) sigue sin herramienta.
- **Dirección Ejecutiva** — Laura Mendoza (informe semanal manual).

Cualquier funcionalidad nueva para estas áreas debe partir de un contexto de hito real (igual que Hitos 1–3), nunca de una suposición.

## Regla de trazabilidad

Ningún dato de negocio (nombre, cifra, responsable, proceso) se añade a este repositorio — código, UI o documentación — sin poder señalarse en una fuente de contexto: `contexts/CONTEXT.md` (o su copia versionada, el `README.md` raíz), un `contexts/hitoN/*.md`, o el documento de contexto de un proyecto versionado en `docs/` (p. ej. `docs/COMPANY_INCIDENT_FILE_ANALIZER_PROJECT.md`). Ver `.agents/rules/nexova-context.md`.

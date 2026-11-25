---
scope: always-active
---

# Regla: fidelidad al contexto de negocio de Nexova

**Alcance (scope):** `always-active` — aplica en toda sesión, no solo al tocar un patrón de archivo concreto, porque un dato de negocio puede colarse en código, UI, documentación o un mensaje de commit por igual. Cubre cualquier dato de negocio (nombre, cifra, responsable, proceso, departamento) que aparezca en este repositorio.

## Regla dura

**No inventar información sobre Nexova.** Todo dato de negocio debe poder señalarse literalmente en:

- `contexts/CONTEXT.md` — briefing completo de la empresa (fuente de verdad principal). **`contexts/` está en `.gitignore` y no viaja con el repositorio** — solo existe en checkouts locales que ya la tenían.
- `docs/briefing.md` — desde el 2026-09-27, copia versionada de `contexts/CONTEXT.md` (contenido idéntico; hasta el 2026-11-25 estaba en el `README.md` raíz). Si no tienes `contexts/`, aquí está el briefing completo.
- `contexts/hito1/CONTEXT-WEB-NEXOVA.md`, `contexts/hito2/CONTEXT-HITO2.md`, `contexts/hito3/CONTEXT-HITO3.md` — briefing específico de cada hito ya construido (solo local, sin copia versionada).
- Documentos de contexto de proyecto versionados en `docs/` (p. ej. `docs/COMPANY_INCIDENT_FILE_ANALIZER_PROJECT.md`, procesador de incidentes).
- `memory-bank/projectbrief.md` — resumen versionado de lo anterior y de lo construido en el repo.

Si un dato no aparece en ninguno de esos archivos, **no se asume ni se rellena por inferencia** — se pregunta, o se marca explícitamente como pendiente de verificar (mismo criterio que `SPECS.md` de `talent-pipeline-tracker` usa para el contrato de API: nada se inventa, todo lo no verificado se marca como tal).

## Casos concretos ya resueltos (no repetir la pregunta)

- Nombre completo: **Nexova Solutions**. Fundada **2011**. Sede **Valencia, España** + oficina de expansión **Miami, Florida**. **120 empleados**, ~**8M USD** de facturación anual. CEO: **Laura Mendoza**.
- Departamentos y responsables: ver tabla en `memory-bank/projectbrief.md`.
- Los valores de `status`/`stage` de la API de `talent-pipeline-tracker` (`received`, `in_progress`, etc.) son datos **técnicos de contrato de API**, no de negocio — esos viven en `SPECS.md` de esa app, no aquí.

## Antes de añadir una funcionalidad nueva para un departamento

Si el departamento (Ventas, RRHH interno, Atención al Cliente, Dirección Ejecutiva) no tiene todavía un hito propio con contexto detallado, **no se implementa la funcionalidad** solo porque `contexts/CONTEXT.md` describe el problema en términos generales — ese briefing es de negocio, no una especificación técnica lista para construir (comparar con el nivel de detalle que sí tienen `contexts/hito1/`, `hito2/`, `hito3/`, cada uno con stakeholder, alcance y criterios de aceptación explícitos).

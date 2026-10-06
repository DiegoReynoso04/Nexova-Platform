---
scope: file-pattern
patterns:
  - "uis/**"
  - "services/**"
  - "agents/**"
  - "mcps/**"
---

# Regla: las reglas locales de cada app priman

**Alcance (scope):** `file-pattern` — se activa al trabajar dentro de cualquier subcarpeta de primer nivel que pueda alojar subproyectos con su propia documentación (`uis/**`, `services/**`, `agents/**`, `mcps/**`). Cubre la relación entre las reglas de `.agents/` (monorepo entero) y la documentación propia de cada subproyecto (`CLAUDE.md`, `AGENTS.md`, `SPECS.md`).

## Regla dura

`.agents/rules/` define el **piso común** del monorepo. Cuando una app tiene su propia documentación de restricciones (por ejemplo `uis/talent-pipeline-tracker/CLAUDE.md` + `SPECS.md`, o `uis/backoffice/CLAUDE.md`), esa documentación **prima dentro de su propio árbol** sobre cualquier regla genérica de aquí. `.agents/` nunca reemplaza ni resume esas reglas — solo remite a ellas.

## Por qué

Cada app puede tener restricciones más estrictas o específicas que no aplican al resto del monorepo (por ejemplo: "prohibido `PATCH` para campos que no sean `status`/`stage`" solo tiene sentido dentro de `talent-pipeline-tracker`, porque depende del contrato de su API concreta). Copiar esas reglas aquí las duplicaría y las dejaría desactualizadas en cuanto cambie el original.

## Documentación local existente hoy

| App | Dónde están sus reglas |
|---|---|
| `uis/talent-pipeline-tracker/` | `CLAUDE.md` (restricciones permanentes) + `SPECS.md` (contrato de API, requisitos funcionales) — ambos versionados |
| `uis/backoffice/` | `CLAUDE.md` (alcance: portada con dato de empresa verificado + `/incidents`, análisis de incidentes + `/suppliers`, directorio de proveedores + autenticación AUTH-02: `/login`, `/register`, `/account/profile` y guard global + contraseñas AUTH-03: `/forgot-password`, `/reset-password`, `/account/change-password`; reglas de arquitectura, privacidad y tests) + `README.md` (configuración y validación) — ambos versionados |
| `services/api/` (procesador de incidentes, Fase 2 + directorio de proveedores) | `SPECS.md` (contrato HTTP; Parte A incidentes con decisiones D-API, Parte B proveedores con decisiones D-SUP; separa requisitos del contexto de Nexova de las decisiones de implementación) + `README.md` (instalación, venv, validación) — ambos versionados |
| `packages/incident-analyzer/` (procesador de incidentes, Fase 1) | `README.md` (API pública, reglas D1–D9, privacidad) — versionado |
| `src/` (Hito 2) | Sin `CLAUDE.md`/`AGENTS.md` propio versionado. `contexts/hito2/HITO2.md` documenta decisiones de diseño y convenciones de test, pero esa carpeta es local y no viaja con el repositorio (ver `nexova-context.md`) — el resumen versionado equivalente está en `memory-bank/techContext.md` |

## Qué hacer ante un conflicto

Si una regla de `.agents/` y una regla local de una app parecen contradecirse, gana la regla local dentro de su propio árbol de carpetas. Si la contradicción no tiene sentido (p. ej. la app local permite algo que el piso común de `.agents/` prohíbe por una razón de negocio, no técnica), no se resuelve por criterio propio — se pregunta antes de proceder.

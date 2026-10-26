---
scope: always-active
---

# Regla: estructura del monorepo

**Alcance (scope):** `always-active` — aplica en toda sesión de agente sobre este repositorio, no solo al tocar un archivo concreto. Convención de carpetas, monorepo entero. No es una regla de negocio ni de una app concreta — para eso ver `nexova-context.md` (también `always-active`) y las reglas propias de cada app (`app-specific-overrides.md`, `file-pattern`).

## Qué hacer antes de crear cualquier carpeta o archivo nuevo

1. Consultar la tabla "Responsabilidad por carpeta" de esta misma regla (abajo) — es la referencia vigente de la convención. *(Hasta el 2026-09-27 la convención vivía en el `README.md` raíz de la plantilla; desde entonces ese archivo es el briefing de Nexova. La guía original completa, con "Guía de carpetas" y "¿Dónde pongo esto?", sigue en el historial: `git show fda5125:README.es.md`.)*
2. Leer el `README.md` de la carpeta de primer nivel donde se va a trabajar (`uis/README.md`, `services/README.md`, `skills/README.md`, etc.) — cada una documenta qué va ahí y qué no.
3. Si la carpeta ya tiene subproyectos (por ejemplo `uis/talent-pipeline-tracker/`), leer también el `README.md`/`CLAUDE.md`/`AGENTS.md` propio de ese subproyecto antes de tocarlo.

## Responsabilidad por carpeta (resumen — el detalle vive en cada README)

| Carpeta | Qué va ahí |
|---|---|
| `uis/` | Frontends — todo lo que un humano ve y en lo que hace clic |
| `services/` | Backend centralizado (FastAPI u otro) — APIs, workers |
| `data/` | raw → pipelines → process → eval |
| `agents/` | Agentes de IA autónomos/semi-autónomos, uno por subcarpeta |
| `skills/` | Capacidades reutilizables para agentes (empaquetadas con `SKILL.md`) |
| `mcps/` | Servidores MCP — acceso en vivo a datos/acciones externas |
| `workflows/` | n8n / automatización entre sistemas |
| `packages/` | Código compartido versionable (tipos, SDKs) |
| `shared/` | Esquemas/plantillas/assets sueltos, no un paquete completo |
| `docs/` | Arquitectura y decisiones transversales |
| `infra/` | Docker, Terraform, CI/CD |
| `scripts/` | Automatización puntual, archivos sueltos |
| `internal/` | CLIs y herramientas con su propio `package.json`/tests |
| `audit/` | Solo evidencias de auditorías (hoy, la de rendimiento con Lighthouse): `before/` y `after/`, con una subcarpeta por app y por página (`<app>/<página>/<página>-<modo>.{png,json}`) y el registro de ejecuciones (`runs.md`). Sin código ni herramientas. El análisis y el informe (`AUDIT.md`, `REPORT.md`) van en la raíz |

## Reglas duras

- No crear una app o servicio nuevo fuera de la carpeta que le corresponde según la tabla anterior.
- No mezclar responsabilidades: un componente de `uis/` no hace llamadas HTTP directas si la app ya tiene una capa `services/` o `lib/api-client.ts` propia (ver la app en cuestión).
- Cada app/servicio/agente nuevo lleva su propia subcarpeta con README — nunca código suelto en la raíz de `uis/`, `services/`, `agents/`, etc.
- No hay workspaces de monorepo configurados en la raíz: cada app Next.js (`uis/talent-pipeline-tracker/`, `uis/backoffice/`) tiene su propio `package.json`/`node_modules` independiente.

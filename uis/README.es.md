# Carpeta `uis`

Esta carpeta contiene **todos los proyectos con interfaz de usuario** para el proyecto transversal de AI Engineering de la compañía — por ejemplo: un sitio web público, un frontend de panel de administración, una interfaz de ecommerce, portales para clientes, aplicaciones Streamlit/Gradio u otras herramientas sólo-frontend.

Los dos proyectos principales que se almacenan aquí son:

- **`website`** — la presencia web pública de la compañía.
- **`backoffice`** — la aplicación interna de administración. Es el lugar ideal para desarrollar múltiples soluciones dentro de un mismo proyecto: autenticación, gestión de personas, gestión de operaciones, comunicación interna y otras capacidades de back-office.

Organiza `uis/` por **distintas áreas de la compañía** — cada subcarpeta agrupa un ámbito diferente (por ejemplo, web pública frente a operaciones internas) e incluye su propia documentación técnica y funcional.

- **Propósito principal**: centralizar en un único lugar todas las aplicaciones frontend que dan soporte a los casos de uso de la compañía.
- **Recomendación**: documenta en este archivo (o en sub-READMEs) las aplicaciones que vayas añadiendo, su objetivo, tecnología usada y cómo ejecutarlas.

## Aplicaciones en este repositorio

| App | Ruta | Objetivo | Stack | Estado |
|---|---|---|---|---|
| Website | [`website/`](./website/) | Landing pública + formulario de registro de talento (Marketing, Carmen Ruiz) | HTML estático + Tailwind CSS v4 (Play CDN), sin build step | Live (Hito 1, desplegado en Netlify) |
| Talent Pipeline Tracker | [`talent-pipeline-tracker/`](./talent-pipeline-tracker/README.md) | Panel interno de gestión de candidaturas (Operaciones de Selección, Javier Almeida) | Next.js 16 (App Router) + React 19 + TypeScript estricto + Tailwind v4 | Hecho (Hito 3). Desde AUTH-02: login/registro/perfil contra `services/api`, todas las vistas exigen sesión; puerto 3001. Desde AUTH-03: recuperar/restablecer/cambiar contraseña |
| Backoffice | [`backoffice/`](./backoffice/README.md) | Punto de entrada del panel administrativo interno de Nexova — ver su README para el alcance | Next.js 16 + React 19 + TypeScript estricto + Tailwind v4 (mismo stack que `talent-pipeline-tracker`, ver [`memory-bank/techContext.md`](../memory-bank/techContext.md)) | Vista de entrada con dato real de empresa + `/incidents`, análisis del CSV de tickets de soporte (Fase 3 del analizador de incidentes) + `/suppliers`, directorio de proveedores (API de almacenamiento ligero); ambos consumen `services/api`. Desde AUTH-02: login/registro/perfil, todas las vistas exigen sesión; puerto 3000. Desde AUTH-03: recuperar/restablecer/cambiar contraseña |

Cómo levantar el sistema completo en local (API, backoffice, tracker, website), puertos, variables de entorno, CORS y validación: [`docs/local-development.md`](../docs/local-development.md).

> _These instructions are also available in [English](./README.md)._

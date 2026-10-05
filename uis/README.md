# `uis` folder

This folder contains **all projects with a user interface** for the cross-functional AI Engineering company project — for example: a public website, admin dashboard frontend, ecommerce UI, customer portals, Streamlit/Gradio app or other frontend-only tools.

The two main projects stored here are:

- **`website`** — the company's public-facing web presence.
- **`backoffice`** — the internal admin application. This is the ideal place to develop multiple solutions within a single project: authentication, people management, operations management, internal communication, and other back-office capabilities.

Organize `uis/` by **different concerns** — each subfolder covers a distinct area of the company (for example, public web vs internal operations) and includes its own technical and functional documentation.

- **Main purpose**: to centralize in a single place all frontend applications that support the company's use cases.
- **Recommendation**: document in this file (or in sub-READMEs) the applications you add, their objective, the technology used, and how to run them.

## Applications in this repository

| App | Path | Objective | Stack | Status |
|---|---|---|---|---|
| Website | [`website/`](./website/) | Public landing + talent registration form (Marketing, Carmen Ruiz) | Static HTML + Tailwind CSS v4 (Play CDN), no build step | Live (Milestone 1, deployed on Netlify) |
| Talent Pipeline Tracker | [`talent-pipeline-tracker/`](./talent-pipeline-tracker/README.md) | Internal candidate-selection panel (Selection Operations, Javier Almeida) | Next.js 16 (App Router) + React 19 + strict TypeScript + Tailwind v4 | Done (Milestone 3). Since AUTH-02: login/register/profile against `services/api`, all views require a session; runs on port 3001 |
| Backoffice | [`backoffice/`](./backoffice/README.md) | Internal admin entry point for Nexova's operations — see its README for scope | Next.js 16 + React 19 + strict TypeScript + Tailwind v4 (same stack as `talent-pipeline-tracker`, see [`memory-bank/techContext.md`](../memory-bank/techContext.md)) | Entry view with real company data + `/incidents` support-ticket CSV analysis (incident analyzer Phase 3) + `/suppliers` supplier directory (lightweight storage API); both consume `services/api`. Since AUTH-02: login/register/profile, all views require a session; port 3000 |

How to run the whole system locally (API, backoffice, tracker, website), ports, environment variables, CORS and validation: [`docs/local-development.md`](../docs/local-development.md) (Spanish).

> _Estas instrucciones también están disponibles en [español](./README.es.md)._

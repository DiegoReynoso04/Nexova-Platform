---
name: memory-bank-sync
description: Sincroniza memory-bank/ (progress.md, techContext.md, projectbrief.md) al cerrar cualquier tarea que cambie código, documentación o una decisión de arquitectura. Úsala siempre antes de comitear o abrir un PR en este monorepo.
---

# memory-bank-sync

## Objetivo

Un único objetivo: dejar `memory-bank/` reflejando con exactitud el estado real del repositorio **inmediatamente antes** de cada commit, para que la siguiente sesión de agente no repita trabajo ni suposiciones ya resueltas. No es un objetivo de "documentar bien" en general — es específicamente mantener sincronizados `progress.md`, `techContext.md` y `projectbrief.md` con lo que el cambio actual acaba de tocar.

## Cuándo se ejecuta

Al terminar cualquier tarea que cambie código, documentación o una decisión de arquitectura en este repositorio — **se vaya a comitear o no** (una sesión que modifica archivos y termina sin commit también deja su entrada). Si hay commit, se ejecuta **antes** del commit/PR: es el paso 4 del flujo de `AGENTS.md` (§4).

**No se ejecuta** en tareas de solo lectura (preguntas, revisiones, exploración) que no modifican archivos del repositorio.

Qué archivo se toca, de un vistazo:

| Archivo | Cuándo |
|---|---|
| `progress.md` | **Siempre** que la tarea modifique archivos del repo. Si ya hay una entrada de hoy sobre el mismo trabajo, se amplía esa en vez de crear otra. |
| `techContext.md` | Solo si cambió algo técnico (ver paso 3). |
| `projectbrief.md` | Solo si cambió algo de negocio (ver paso 4). Casi nunca. |

## Inputs

- `git status --short` y `git diff --stat` de la rama de trabajo frente a su base — la lista real de archivos tocados, no una suposición.
- El contenido actual de `memory-bank/progress.md`, `memory-bank/techContext.md` y `memory-bank/projectbrief.md` (para saber qué corregir, no solo qué añadir).
- El contexto de negocio disponible: `contexts/CONTEXT.md` si existe en el checkout local, o su copia versionada en `docs/briefing.md`, más `memory-bank/projectbrief.md` (ver `.agents/rules/nexova-context.md`).
- La fecha actual (`AAAA-MM-DD`), para fechar la entrada nueva.

## Procedimiento

1. **Listar qué cambió realmente:** `git status --short` y/o `git diff --stat` frente a la base de la rama. No asumir — leer la lista real de archivos tocados (input #1).
2. **Añadir una entrada a `memory-bank/progress.md`:**
   - Fecha de hoy, como nueva sección **arriba** del archivo (las entradas más recientes van primero).
   - Qué cambió, por qué (una frase de contexto), y estado (`hecho` / `en curso` / `bloqueado`).
   - Si esta entrada corrige o vuelve obsoleta una entrada anterior, **corregir esa entrada anterior** (o marcarla explícitamente como superada) — nunca dejar dos entradas contradictorias sin resolver.
3. **Actualizar `memory-bank/techContext.md` si y solo si cambió algo técnico:** nueva app/servicio, cambio de stack, nueva decisión de arquitectura, dependencia añadida. Si no hay cambio técnico, no tocar el archivo — no rellenar por rellenar.
4. **Actualizar `memory-bank/projectbrief.md` si y solo si cambió algo de negocio:** nuevo hito con contexto propio, nuevo stakeholder, nuevo departamento con app asociada. Esto es infrecuente — la mayoría de las tareas no lo requieren.
5. **Revisar que ninguna ruta, archivo, comando o endpoint mencionado en `memory-bank/` haya dejado de existir** como consecuencia del propio cambio (por ejemplo: un archivo renombrado, un endpoint retirado). Corregir la mención, no dejarla colgando.

## Criterios de aceptación (verificables, no de intención)

- [ ] `memory-bank/progress.md` tiene una entrada fechada con el día de hoy, describiendo el cambio recién hecho, con estado explícito.
- [ ] Si el cambio tocó algo bajo `uis/`, `services/`, `agents/`, `data/`, `packages/`, `shared/`, `.agents/` o `src/`, `techContext.md` refleja ese cambio — **o** la entrada de `progress.md` dice explícitamente "sin impacto técnico".
- [ ] Ninguna ruta/archivo/comando citado en `memory-bank/*.md` falla al verificarse contra el estado actual del repo (chequeo con `Glob`/`Grep`/`ls` sobre las rutas citadas).
- [ ] No quedan dos entradas de `progress.md` que se contradigan sobre el mismo tema (por ejemplo, una que diga "pendiente" y otra más reciente que diga "hecho" para lo mismo, sin que la primera se haya corregido).

## Idempotencia

Ejecutar esta skill una segunda vez **sin cambios nuevos de por medio** no debe producir un segundo diff en `memory-bank/`: al re-recorrer los pasos 1–5, si `git status`/`git diff --stat` no muestran nada nuevo desde la última ejecución, no se escribe nada — no se duplica la entrada de `progress.md` ni se re-toca `techContext.md`/`projectbrief.md` sin motivo. La skill es segura de re-invocar por precaución.

## Cómo se verificó que funciona (no solo que está descrita)

La propia entrada de `memory-bank/progress.md` fechada el día en que se implementó esta skill (tarea "Monorepo AI Setup") es su primera ejecución real — se escribió siguiendo estos mismos pasos, no como ejemplo hipotético.

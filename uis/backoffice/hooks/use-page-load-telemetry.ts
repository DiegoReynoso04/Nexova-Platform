// `page_load_recorded` (plan §6.8): del montaje de la vista a su primer estado
// final (datos, vacío o error), una vez por montaje. Lo usan las 4 páginas de
// datos del plan con el estado que ya calculan sus hooks.

import { useEffect, useRef, useState } from 'react';

import { elapsedMs, track } from '@/lib/telemetry';
import type { LoadedPageRouteTemplate, PageLoadOutcome } from '@/types/telemetry';

/** Tope del esquema de `duration_ms` (event-schemas.json). */
const PAGE_LOAD_MAX_MS = 120_000;

/** Estado de la vista (`'loading' | 'error' | 'empty' | 'data'`) → resultado, o `null` mientras carga. */
export function pageLoadOutcome(view: 'loading' | 'error' | 'empty' | 'data'): PageLoadOutcome | null {
  return view === 'loading' ? null : view;
}

function now(): number {
  return typeof performance === 'undefined' ? Date.now() : performance.now();
}

export function usePageLoadTelemetry(route: LoadedPageRouteTemplate, outcome: PageLoadOutcome | null): void {
  const [startedAt] = useState(now);
  const recorded = useRef(false);

  useEffect(() => {
    if (outcome === null || recorded.current) return;
    recorded.current = true;
    track('page_load_recorded', { route_template: route, duration_ms: elapsedMs(startedAt, now(), PAGE_LOAD_MAX_MS), outcome });
  }, [outcome, route, startedAt]);
}

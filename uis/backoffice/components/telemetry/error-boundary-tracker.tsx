'use client';

// `frontend_error_captured` (plan §6.6) al montarse un límite de error: solo
// cuál (`route` o `global`) y la plantilla de la página. **El error no se lee**
// (ni mensaje, ni `digest`, ni traza): este componente ni lo recibe. Throttle
// de 60 s por (límite, página) en lib/telemetry.ts. No pinta nada.

import { useEffect } from 'react';

import { pageRouteTemplate, trackThrottled } from '@/lib/telemetry';
import type { ErrorBoundaryKind } from '@/types/telemetry';

export function ErrorBoundaryTracker({ boundary }: { boundary: ErrorBoundaryKind }) {
  useEffect(() => {
    const route = pageRouteTemplate(window.location.pathname);
    trackThrottled(`${boundary}:${route ?? 'none'}`, 'frontend_error_captured', (suppressedCount) => ({
      boundary,
      route_template: route,
      suppressed_count: suppressedCount,
    }));
  }, [boundary]);
  return null;
}

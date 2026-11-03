// `page_viewed` (plan §6.4) sin React: una vista cuenta si la ruta se mantiene
// 1 s (descarta redirecciones como `/inventory` → `/inventory/products` o el
// guard → `/login`). Solo plantillas del plan: nunca el path real ni la query
// string (`?token=` de /reset-password es un secreto). La usa
// components/telemetry/page-view-tracker.tsx; la página anterior sirve también
// a `page_not_found_viewed`.

import { pageRouteTemplate, track } from '@/lib/telemetry';
import type { PageRouteTemplate, TelemetryEventProperties, TelemetryEventType } from '@/types/telemetry';

export const PAGE_VIEW_DWELL_MS = 1_000;

type Track = <E extends TelemetryEventType>(eventType: E, properties: TelemetryEventProperties[E]) => void;

export interface PageViewTelemetry {
  /** Cambio de `usePathname()`. */
  navigated(pathname: string): void;
  /** Última página contada (para `page_not_found_viewed`). */
  previous(): PageRouteTemplate | null;
  dispose(): void;
}

export function createPageViewTelemetry(emit: Track = track): PageViewTelemetry {
  let timer: ReturnType<typeof setTimeout> | null = null;
  let previous: PageRouteTemplate | null = null;
  let counted = 0;

  return {
    navigated(pathname) {
      if (timer !== null) clearTimeout(timer);
      timer = null;
      const route = pageRouteTemplate(pathname);
      if (route === null) return; // 404 u otra ruta: la cuenta not-found.tsx
      timer = setTimeout(() => {
        timer = null;
        emit('page_viewed', {
          route_template: route,
          previous_route_template: previous,
          entry: counted === 0 ? 'initial_load' : 'in_app_navigation',
        });
        previous = route;
        counted += 1;
      }, PAGE_VIEW_DWELL_MS);
    },
    previous: () => previous,
    dispose() {
      if (timer !== null) clearTimeout(timer);
      timer = null;
    },
  };
}

/** Una por pestaña: la comparten el tracker del layout y la página 404. */
export const pageViewTelemetry = createPageViewTelemetry();

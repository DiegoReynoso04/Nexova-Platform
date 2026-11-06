'use client';

// `page_not_found_viewed` (plan §6.4) al montarse la página 404: solo la página
// anterior del backoffice, nunca el path pedido (texto arbitrario). No pinta nada.
// Una vez por montaje: en `next dev`, StrictMode ejecuta los efectos dos veces.

import { useEffect, useRef } from 'react';

import { pageViewTelemetry } from '@/lib/page-view-telemetry';
import { track } from '@/lib/telemetry';

export function NotFoundTracker() {
  const recorded = useRef(false);

  useEffect(() => {
    if (recorded.current) return;
    recorded.current = true;
    track('page_not_found_viewed', { previous_route_template: pageViewTelemetry.previous() });
  }, []);
  return null;
}

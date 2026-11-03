'use client';

// `page_not_found_viewed` (plan §6.4) al montarse la página 404: solo la página
// anterior del backoffice, nunca el path pedido (texto arbitrario). No pinta nada.

import { useEffect } from 'react';

import { pageViewTelemetry } from '@/lib/page-view-telemetry';
import { track } from '@/lib/telemetry';

export function NotFoundTracker() {
  useEffect(() => {
    track('page_not_found_viewed', { previous_route_template: pageViewTelemetry.previous() });
  }, []);
  return null;
}

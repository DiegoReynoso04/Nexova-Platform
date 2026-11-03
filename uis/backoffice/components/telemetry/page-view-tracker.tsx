'use client';

// `page_viewed` en el layout raíz (plan §6.4): cada cambio de ruta que se
// mantiene 1 s. La lógica está en lib/page-view-telemetry.ts. No pinta nada.

import { usePathname } from 'next/navigation';
import { useEffect } from 'react';

import { pageViewTelemetry } from '@/lib/page-view-telemetry';

export function PageViewTracker() {
  const pathname = usePathname();
  useEffect(() => {
    pageViewTelemetry.navigated(pathname);
  }, [pathname]);
  return null;
}

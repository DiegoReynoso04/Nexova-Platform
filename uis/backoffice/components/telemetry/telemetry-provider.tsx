'use client';

// Arranca la telemetría del backoffice una vez (lib/telemetry.ts → startTelemetry):
// envío por `sendBeacon` al ocultar o cerrar la pestaña y `client_request_failed`
// para los fallos de red de cualquier cliente HTTP. No pinta nada.

import { useEffect } from 'react';

import { startTelemetry } from '@/lib/telemetry';

export function TelemetryProvider() {
  useEffect(() => startTelemetry(), []);
  return null;
}

// Embudo de un formulario (lib/form-telemetry.ts) con el ciclo de vida de React:
// una instancia por vista (sobrevive a que el formulario se vuelva a montar
// limpio tras un éxito) y `form_abandoned` al desmontar o en `pagehide`.
//
// `pagehide` se escucha en fase de captura: así el abandono entra en la cola
// antes de que lib/telemetry.ts la envíe con `sendBeacon` en ese mismo evento.

import { useEffect, useState } from 'react';

import { createFormTelemetry, type FormTelemetry } from '@/lib/form-telemetry';
import type { TelemetryForm } from '@/types/telemetry';

export function useFormTelemetry(form: TelemetryForm): FormTelemetry {
  const [telemetry] = useState(() => createFormTelemetry(form));

  useEffect(() => {
    const onPageHide = () => telemetry.abandon();
    window.addEventListener('pagehide', onPageHide, { capture: true });
    return () => {
      window.removeEventListener('pagehide', onPageHide, { capture: true });
      telemetry.abandon();
    };
  }, [telemetry]);

  return telemetry;
}

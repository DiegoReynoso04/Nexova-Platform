'use client';

// Franja «Datos actualizados» de /reporting: cuándo terminó la última corrida del pipeline.
// Con su propia carga y su propio error: si falla, el reporte sigue visible. Sin códigos ni
// nombres técnicos (nada de fase, contadores ni `error_class`).

import { useState } from 'react';

import { Alert } from '@/components/ui/alert';
import { Button } from '@/components/ui/button';
import { usePipelineFreshness } from '@/hooks/use-pipeline-freshness';
import { STALE_NOTICE, describeFreshness, reportingErrorCopy } from '@/lib/reporting-format';

const PANEL = 'rounded-lg border border-border bg-surface px-4 py-3 text-sm text-ink';

export function DataFreshness() {
  const { run, load, reload } = usePipelineFreshness();
  // Fijo durante la vida de la vista: el aviso de «desactualizado» se calcula contra el momento de abrirla.
  const [now] = useState(() => new Date());

  if (load.status === 'error') {
    return (
      <div className="flex flex-col gap-2">
        <Alert variant="error" title="No se pudo comprobar cuándo se actualizaron los datos">
          {reportingErrorCopy(load.error).body}
        </Alert>
        <div>
          <Button variant="secondary" onClick={reload}>
            Reintentar
          </Button>
        </div>
      </div>
    );
  }

  if (load.status !== 'success') {
    return (
      <p role="status" className={`${PANEL} text-ink-muted`}>
        Comprobando la última actualización…
      </p>
    );
  }

  const freshness = describeFreshness(run, now);
  return (
    <div className="flex flex-col gap-2">
      {freshness.tone === 'info' && <Alert variant="info" title={freshness.headline} />}
      {freshness.tone === 'problem' && <Alert variant="error" title={freshness.headline} />}
      {(freshness.tone === 'ok' || freshness.tone === 'none') && (
        <div className={PANEL}>
          <p className="font-semibold">{freshness.headline}</p>
          {freshness.detail !== null && <p className="text-ink-muted">{freshness.detail}</p>}
        </div>
      )}
      {freshness.stale && <Alert variant="error" title={STALE_NOTICE} />}
    </div>
  );
}

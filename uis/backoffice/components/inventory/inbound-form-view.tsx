'use client';

// Vista de /inventory/orders/inbound: carga los activos para el selector
// (useInventoryAssets) y envía la entrada (useInboundForm). No hace HTTP.
// Tras una entrada correcta: confirmación visible y formulario limpio
// (`key = formKey`), con el activo de la URL preseleccionado si lo había.

import { Alert } from '@/components/ui/alert';
import { inboundConfirmation, useInboundForm } from '@/hooks/use-inbound-form';
import { useInventoryAssets } from '@/hooks/use-inventory-assets';
import { formInitialAssetId, resolvePreselection, type AssetIdParam } from '@/lib/asset-preselection';

import { InboundForm } from './inbound-form';

const MISSING_ASSET_NOTICE = 'El activo del enlace no existe en el inventario. Elige uno de la lista.';

export interface InboundFormViewProps {
  /** `?asset_id=` de la URL, ya leído por la página. */
  assetIdParam: AssetIdParam;
  /** Id del `h1` de la página, que da nombre a la sección. */
  labelledBy: string;
}

export function InboundFormView({ assetIdParam, labelledBy }: InboundFormViewProps) {
  const assets = useInventoryAssets();
  const { submit, formKey, submitInbound } = useInboundForm();
  const preselection = resolvePreselection(assetIdParam, assets.loaded ? assets.assets : null);
  const loadError = assets.load.status === 'error' ? assets.load.error : null;

  return (
    <section aria-labelledby={labelledBy} className="flex flex-col gap-4 rounded-lg border border-border bg-surface p-4 sm:p-6">
      {submit.status === 'success' && (
        <Alert variant="info" title={inboundConfirmation(submit.order)}>
          <p>El formulario está listo para otra entrada.</p>
        </Alert>
      )}

      {/* key: tras una entrada correcta, o al resolverse la preselección, el formulario se vuelve a montar. */}
      <InboundForm
        key={`${formKey}-${preselection.status}`}
        view={assets.view}
        assets={assets.assets}
        loadError={loadError}
        onRetryAssets={assets.reload}
        initialAssetId={formInitialAssetId(preselection)}
        notice={preselection.status === 'missing' ? MISSING_ASSET_NOTICE : null}
        submit={submit}
        onSubmit={submitInbound}
      />
    </section>
  );
}

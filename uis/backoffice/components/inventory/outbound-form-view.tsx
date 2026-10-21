'use client';

// Vista de /inventory/orders/outbound: carga los activos para el selector
// (useInventoryAssets) y lleva el activo elegido, su stock y el envío
// (useOutboundForm). No hace HTTP. El activo de la URL se elige al resolverse
// la preselección, y también es el que queda tras una salida correcta.

import { useEffect } from 'react';

import { Alert } from '@/components/ui/alert';
import { useInventoryAssets } from '@/hooks/use-inventory-assets';
import { outboundConfirmation, useOutboundForm } from '@/hooks/use-outbound-form';
import { formInitialAssetId, resolvePreselection, type AssetIdParam } from '@/lib/asset-preselection';
import type { OutboundFormValues } from '@/types/inventory';

import { OutboundForm } from './outbound-form';

const MISSING_ASSET_NOTICE = 'El activo del enlace no existe en el inventario. Elige uno de la lista.';

export interface OutboundFormViewProps {
  /** `?asset_id=` de la URL, ya leído por la página. */
  assetIdParam: AssetIdParam;
  /** Id del `h1` de la página, que da nombre a la sección. */
  labelledBy: string;
}

export function OutboundFormView({ assetIdParam, labelledBy }: OutboundFormViewProps) {
  const assets = useInventoryAssets();
  const { assetId, stock, submit, formKey, selectAsset, submitOutbound } = useOutboundForm();
  const preselection = resolvePreselection(assetIdParam, assets.loaded ? assets.assets : null);
  const initialAssetId = formInitialAssetId(preselection);
  const loadError = assets.load.status === 'error' ? assets.load.error : null;

  // Al resolverse la preselección, se elige el activo de la URL y se lee su stock.
  useEffect(() => {
    if (initialAssetId !== null) selectAsset(initialAssetId);
  }, [initialAssetId, selectAsset]);

  function handleSubmit(values: OutboundFormValues) {
    submitOutbound(values, initialAssetId);
  }

  return (
    <section aria-labelledby={labelledBy} className="flex flex-col gap-4 rounded-lg border border-border bg-surface p-4 sm:p-6">
      {submit.status === 'success' && (
        <Alert variant="info" title={outboundConfirmation(submit.order)}>
          <p>El formulario está listo para otra salida.</p>
        </Alert>
      )}

      {/* key: tras una salida correcta, el formulario se vuelve a montar limpio. */}
      <OutboundForm
        key={formKey}
        view={assets.view}
        assets={assets.assets}
        loadError={loadError}
        onRetryAssets={assets.reload}
        assetId={assetId}
        onAssetChange={selectAsset}
        stock={stock}
        notice={preselection.status === 'missing' ? MISSING_ASSET_NOTICE : null}
        submit={submit}
        onSubmit={handleSubmit}
      />
    </section>
  );
}

'use client';

import { useEffect, useRef, useState, type FormEvent } from 'react';

import { Button } from '@/components/ui/button';
import type { AssetsView } from '@/hooks/use-inventory-assets';
import type { InboundSubmitState } from '@/hooks/use-inbound-form';
import { fieldMessages, summaryError, unplacedMessages } from '@/lib/inventory-form-errors';
import type { Asset, InboundFormValues, InventoryField, InventoryUiError } from '@/types/inventory';

import { AssetSelect, CONTROL_CLASSES } from './asset-select';
import { FieldMessages } from './field-messages';
import { InventoryError } from './inventory-error';
import { ReadOnlyField } from './read-only-field';

// Formulario de Entrada de activos (POST /inventory/orders/inbound). No hace
// HTTP: entrega los valores a la vista (useInboundForm). La oficina no la
// elige el usuario: es la del activo, en solo lectura, y es la que se envía.
// La validación en cliente la hace el servicio antes de enviar.

const FORM_FIELDS: readonly InventoryField[] = ['asset_id', 'quantity', 'supplier', 'office'];

export interface InboundFormProps {
  view: AssetsView;
  assets: readonly Asset[];
  loadError: InventoryUiError | null;
  onRetryAssets: () => void;
  /** Activo preseleccionado (por `?asset_id=`); se mantiene tras una entrada correcta. */
  initialAssetId: number | null;
  notice: string | null;
  submit: InboundSubmitState;
  onSubmit: (values: InboundFormValues) => void;
}

export function InboundForm({ view, assets, loadError, onRetryAssets, initialAssetId, notice, submit, onSubmit }: InboundFormProps) {
  const [assetId, setAssetId] = useState<number | null>(initialAssetId);
  const [quantity, setQuantity] = useState('');
  const [supplier, setSupplier] = useState('');
  const [attempt, setAttempt] = useState(0);

  const selected = assets.find((asset) => asset.id === assetId) ?? null;
  const isSubmitting = submit.status === 'submitting';
  const error = submit.status === 'error' ? submit.error : null;
  const summary = summaryError(error, FORM_FIELDS);
  const unplaced = unplacedMessages(error, FORM_FIELDS);
  const quantityMessages = fieldMessages(error, 'quantity');
  const supplierMessages = fieldMessages(error, 'supplier');

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setAttempt((current) => current + 1);
    onSubmit({ asset: selected === null ? null : { id: selected.id, office: selected.office }, quantity, supplier });
  }

  // Tras un intento fallido, el foco va al aviso general (si lo hay).
  const summaryRef = useRef<HTMLDivElement>(null);
  const hasSummary = summary !== null;
  useEffect(() => {
    if (attempt > 0 && hasSummary) summaryRef.current?.focus();
  }, [attempt, hasSummary, error]);

  return (
    <form onSubmit={handleSubmit} noValidate className="flex flex-col gap-4" aria-describedby="inbound-form-help">
      <p id="inbound-form-help" className="text-xs text-ink-muted">
        Los campos marcados con * son obligatorios.
      </p>

      {summary !== null && (
        <div ref={summaryRef} tabIndex={-1} className="flex flex-col gap-2 outline-none">
          <InventoryError error={summary} />
          <FieldMessages id="inbound-form-general" messages={unplaced} />
        </div>
      )}

      <AssetSelect
        id="inbound-asset"
        view={view}
        assets={assets}
        loadError={loadError}
        onRetry={onRetryAssets}
        value={assetId}
        onChange={setAssetId}
        messages={fieldMessages(error, 'asset_id')}
        notice={notice}
        disabled={isSubmitting}
      />

      <ReadOnlyField
        id="inbound-office"
        label="Oficina"
        value={selected?.office ?? null}
        placeholder="Se toma del activo elegido"
        help="La oficina receptora es la del activo: no se puede cambiar aquí."
        messages={fieldMessages(error, 'office')}
      />

      <div className="flex flex-col gap-1">
        <label htmlFor="inbound-quantity" className="text-sm font-medium text-ink">
          Cantidad *
        </label>
        <input
          id="inbound-quantity"
          inputMode="numeric"
          autoComplete="off"
          value={quantity}
          onChange={(event) => setQuantity(event.target.value)}
          disabled={isSubmitting}
          aria-invalid={quantityMessages.length > 0 || undefined}
          aria-describedby={quantityMessages.length > 0 ? 'inbound-quantity-messages' : undefined}
          className={`${CONTROL_CLASSES} ${quantityMessages.length > 0 ? 'border-danger-ink' : 'border-border'}`}
        />
        <FieldMessages id="inbound-quantity-messages" messages={quantityMessages} />
      </div>

      <div className="flex flex-col gap-1">
        <label htmlFor="inbound-supplier" className="text-sm font-medium text-ink">
          Proveedor *
        </label>
        <input
          id="inbound-supplier"
          autoComplete="off"
          value={supplier}
          onChange={(event) => setSupplier(event.target.value)}
          disabled={isSubmitting}
          aria-invalid={supplierMessages.length > 0 || undefined}
          aria-describedby={supplierMessages.length > 0 ? 'inbound-supplier-messages' : undefined}
          className={`${CONTROL_CLASSES} ${supplierMessages.length > 0 ? 'border-danger-ink' : 'border-border'}`}
        />
        <FieldMessages id="inbound-supplier-messages" messages={supplierMessages} />
      </div>

      <div>
        <Button type="submit" isLoading={isSubmitting}>
          {isSubmitting ? 'Registrando…' : 'Registrar entrada'}
        </Button>
      </div>
    </form>
  );
}

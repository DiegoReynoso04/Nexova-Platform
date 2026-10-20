'use client';

import { useEffect, useRef, useState, type FormEvent } from 'react';

import { Button } from '@/components/ui/button';
import { LoadingSpinner } from '@/components/ui/loading-spinner';
import type { AssetsView } from '@/hooks/use-inventory-assets';
import { knownStock, outboundFormValues, quantityEnabled, type OutboundSubmitState, type StockState } from '@/hooks/use-outbound-form';
import { fieldMessages, summaryError, unplacedMessages } from '@/lib/inventory-form-errors';
import { exceedsStock } from '@/lib/stock-check';
import type { Asset, ExitType, InventoryField, InventoryUiError, OutboundFormValues } from '@/types/inventory';

import { AssetSelect, CONTROL_CLASSES } from './asset-select';
import { FieldMessages } from './field-messages';
import { InventoryError } from './inventory-error';
import { ReadOnlyField } from './read-only-field';
import { StockLevelBadge } from './stock-level-badge';

// Formulario de Salida de activos (POST /inventory/orders/outbound). No hace
// HTTP: el activo elegido y su stock vienen de la vista (useOutboundForm), y
// los valores se le entregan al enviar. Orden de los campos: Activo, Stock
// actual y Oficina (solo lectura), Tipo de salida, Asignado a (solo con una
// asignación) y Cantidad. Una cantidad mayor que el stock muestra una
// advertencia que no bloquea el envío: la API es la autoridad.

const BASE_FIELDS: readonly InventoryField[] = ['asset_id', 'quantity', 'exit_type', 'office'];
const ALLOCATION_FIELDS: readonly InventoryField[] = [...BASE_FIELDS, 'assigned_to'];

const EXIT_TYPE_OPTIONS: readonly { value: ExitType; label: string; hint: string }[] = [
  { value: 'allocation', label: 'Asignación', hint: 'allocation: a un empleado' },
  { value: 'consumption', label: 'Consumo', hint: 'consumption: material que se gasta, p. ej., papel' },
];

export interface OutboundFormProps {
  view: AssetsView;
  assets: readonly Asset[];
  loadError: InventoryUiError | null;
  onRetryAssets: () => void;
  assetId: number | null;
  onAssetChange: (assetId: number | null) => void;
  stock: StockState;
  notice: string | null;
  submit: OutboundSubmitState;
  onSubmit: (values: OutboundFormValues) => void;
}

function StockValue({ stock }: { stock: StockState }) {
  const current = knownStock(stock);
  if (stock.status === 'loading' && current === null) {
    return (
      <span className="inline-flex items-center gap-2 text-ink-muted">
        <LoadingSpinner size="sm" />
        Consultando stock…
      </span>
    );
  }
  if (current === null) return <span className="text-ink-muted">No disponible</span>;
  return (
    <span className="inline-flex items-center gap-2">
      <span className="font-semibold tabular-nums">{current}</span>
      <StockLevelBadge currentStock={current} />
      {stock.status === 'loading' && <span className="text-xs text-ink-muted">Actualizando…</span>}
    </span>
  );
}

export function OutboundForm({
  view,
  assets,
  loadError,
  onRetryAssets,
  assetId,
  onAssetChange,
  stock,
  notice,
  submit,
  onSubmit,
}: OutboundFormProps) {
  const [quantity, setQuantity] = useState('');
  const [exitType, setExitType] = useState<ExitType | ''>('');
  const [assignedTo, setAssignedTo] = useState('');
  const [attempt, setAttempt] = useState(0);

  const selected = assets.find((asset) => asset.id === assetId) ?? null;
  const isSubmitting = submit.status === 'submitting';
  const error = submit.status === 'error' ? submit.error : null;
  // Con un consumo no se ve «Asignado a»: sus errores, si llegan, van al aviso general.
  const formFields = exitType === 'allocation' ? ALLOCATION_FIELDS : BASE_FIELDS;
  const summary = summaryError(error, formFields);
  const unplaced = unplacedMessages(error, formFields);
  const quantityMessages = fieldMessages(error, 'quantity');
  const exitTypeMessages = fieldMessages(error, 'exit_type');
  const assignedToMessages = fieldMessages(error, 'assigned_to');
  const currentStock = knownStock(stock);
  const showWarning = exceedsStock(quantity, currentStock);

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setAttempt((value) => value + 1);
    // La advertencia de stock no impide enviar.
    onSubmit(outboundFormValues(selected === null ? null : { id: selected.id, office: selected.office }, quantity, exitType, assignedTo));
  }

  // Tras un intento fallido, el foco va al aviso general (si lo hay).
  const summaryRef = useRef<HTMLDivElement>(null);
  const hasSummary = summary !== null;
  useEffect(() => {
    if (attempt > 0 && hasSummary) summaryRef.current?.focus();
  }, [attempt, hasSummary, error]);

  const quantityDescribedBy = ['outbound-quantity-warning', quantityMessages.length > 0 ? 'outbound-quantity-messages' : null]
    .filter((item) => item !== null)
    .join(' ');

  return (
    <form onSubmit={handleSubmit} noValidate className="flex flex-col gap-4" aria-describedby="outbound-form-help">
      <p id="outbound-form-help" className="text-xs text-ink-muted">
        Los campos marcados con * son obligatorios.
      </p>

      {summary !== null && (
        <div ref={summaryRef} tabIndex={-1} className="flex flex-col gap-2 outline-none">
          <InventoryError error={summary} />
          <FieldMessages id="outbound-form-general" messages={unplaced} />
        </div>
      )}

      <AssetSelect
        id="outbound-asset"
        view={view}
        assets={assets}
        loadError={loadError}
        onRetry={onRetryAssets}
        value={assetId}
        onChange={onAssetChange}
        messages={fieldMessages(error, 'asset_id')}
        notice={notice}
        disabled={isSubmitting}
      />

      <div className="flex flex-col gap-1">
        <ReadOnlyField
          id="outbound-stock"
          label="Stock actual"
          value={selected === null ? null : <StockValue stock={stock} />}
          placeholder="Elige un activo para ver su stock"
        />
        {selected !== null && stock.status === 'error' && (
          <p role="status" className="text-xs font-medium text-warning-ink">
            No se pudo consultar el stock. Puedes registrar la salida igualmente: la API comprobará si hay stock suficiente.
          </p>
        )}
      </div>

      <ReadOnlyField
        id="outbound-office"
        label="Oficina"
        value={selected?.office ?? null}
        placeholder="Se toma del activo elegido"
        help="La oficina de la salida es la del activo: no se puede cambiar aquí."
        messages={fieldMessages(error, 'office')}
      />

      <fieldset
        className="flex flex-col gap-1"
        aria-invalid={exitTypeMessages.length > 0 || undefined}
        aria-describedby={exitTypeMessages.length > 0 ? 'outbound-exit-type-messages' : undefined}
      >
        <legend className="text-sm font-medium text-ink">Tipo de salida *</legend>
        <div className="flex flex-col gap-2 sm:flex-row sm:gap-6">
          {EXIT_TYPE_OPTIONS.map((option) => (
            <label key={option.value} className="flex items-start gap-2 text-sm text-ink">
              <input
                type="radio"
                name="exit_type"
                value={option.value}
                checked={exitType === option.value}
                onChange={() => setExitType(option.value)}
                disabled={isSubmitting}
                className="mt-0.5"
              />
              <span className="flex flex-col">
                <span className="font-medium">{option.label}</span>
                <span className="text-xs text-ink-muted">{option.hint}</span>
              </span>
            </label>
          ))}
        </div>
        <FieldMessages id="outbound-exit-type-messages" messages={exitTypeMessages} />
      </fieldset>

      {exitType === 'allocation' && (
        <div className="flex flex-col gap-1">
          <label htmlFor="outbound-assigned-to" className="text-sm font-medium text-ink">
            Asignado a *
          </label>
          <input
            id="outbound-assigned-to"
            autoComplete="off"
            value={assignedTo}
            onChange={(event) => setAssignedTo(event.target.value)}
            disabled={isSubmitting}
            aria-invalid={assignedToMessages.length > 0 || undefined}
            aria-describedby={assignedToMessages.length > 0 ? 'outbound-assigned-to-help outbound-assigned-to-messages' : 'outbound-assigned-to-help'}
            className={`${CONTROL_CLASSES} ${assignedToMessages.length > 0 ? 'border-danger-ink' : 'border-border'}`}
          />
          <p id="outbound-assigned-to-help" className="text-xs text-ink-muted">
            Nombre o identificador del empleado que recibe el activo.
          </p>
          <FieldMessages id="outbound-assigned-to-messages" messages={assignedToMessages} />
        </div>
      )}

      <div className="flex flex-col gap-1">
        <label htmlFor="outbound-quantity" className="text-sm font-medium text-ink">
          Cantidad *
        </label>
        <input
          id="outbound-quantity"
          inputMode="numeric"
          autoComplete="off"
          value={quantity}
          onChange={(event) => setQuantity(event.target.value)}
          disabled={isSubmitting || !quantityEnabled(stock)}
          aria-invalid={quantityMessages.length > 0 || undefined}
          aria-describedby={quantityDescribedBy}
          className={`${CONTROL_CLASSES} ${quantityMessages.length > 0 ? 'border-danger-ink' : 'border-border'}`}
        />
        {!quantityEnabled(stock) && (
          <p className="text-xs text-ink-muted">{selected === null ? 'Elige un activo para indicar la cantidad.' : 'Espera a conocer el stock.'}</p>
        )}
        <div id="outbound-quantity-warning" aria-live="polite">
          {showWarning && currentStock !== null && (
            <p className="text-xs font-medium text-warning-ink">
              <span aria-hidden="true">! </span>
              La cantidad supera el stock actual, que es {currentStock}. Puedes registrar la salida igualmente: la API comprobará el stock.
            </p>
          )}
        </div>
        <FieldMessages id="outbound-quantity-messages" messages={quantityMessages} alert={error?.kind === 'api_error'} />
      </div>

      <div>
        <Button type="submit" isLoading={isSubmitting}>
          {isSubmitting ? 'Registrando…' : 'Registrar salida'}
        </Button>
      </div>
    </form>
  );
}

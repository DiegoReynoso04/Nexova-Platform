import { Alert } from '@/components/ui/alert';
import { Button } from '@/components/ui/button';
import { LoadingSpinner } from '@/components/ui/loading-spinner';
import type { AssetsView } from '@/hooks/use-inventory-assets';
import { assetOptionLabel } from '@/lib/asset-preselection';
import type { FieldMessage } from '@/lib/inventory-form-errors';
import type { Asset, InventoryUiError } from '@/types/inventory';

import { FieldMessages } from './field-messages';
import { InventoryError } from './inventory-error';

// Selector de activo de los formularios de entrada y salida (presentacional).
// Cada opción muestra «nombre — SKU (oficina)», nunca el id: hay nombres
// repetidos. La lista la carga la vista con useInventoryAssets.

export const CONTROL_CLASSES =
  'w-full rounded-control border bg-surface px-3 py-2 text-sm text-ink outline-none focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand disabled:cursor-not-allowed disabled:bg-canvas';

export interface AssetSelectProps {
  id: string;
  view: AssetsView;
  assets: readonly Asset[];
  loadError: InventoryUiError | null;
  onRetry: () => void;
  value: number | null;
  onChange: (assetId: number | null) => void;
  messages: readonly FieldMessage[];
  /** Aviso visible si el `?asset_id=` de la URL no existe. */
  notice: string | null;
  disabled?: boolean;
}

export function AssetSelect({ id, view, assets, loadError, onRetry, value, onChange, messages, notice, disabled = false }: AssetSelectProps) {
  const messagesId = `${id}-messages`;
  const hasMessages = messages.length > 0;

  function handleChange(raw: string) {
    const match = assets.find((asset) => String(asset.id) === raw);
    onChange(match === undefined ? null : match.id);
  }

  return (
    <div className="flex flex-col gap-1">
      <label htmlFor={id} className="text-sm font-medium text-ink">
        Activo *
      </label>

      {view === 'error' && loadError !== null ? (
        <div className="flex flex-col gap-2">
          <InventoryError error={loadError} />
          <div>
            <Button variant="secondary" onClick={onRetry}>
              Reintentar
            </Button>
          </div>
        </div>
      ) : (
        <div className="flex items-center gap-2">
          <select
            id={id}
            value={value === null ? '' : String(value)}
            onChange={(event) => handleChange(event.target.value)}
            disabled={disabled || view !== 'data'}
            aria-invalid={hasMessages || undefined}
            aria-describedby={hasMessages ? messagesId : undefined}
            className={`${CONTROL_CLASSES} ${hasMessages ? 'border-danger-ink' : 'border-border'}`}
          >
            {view === 'loading' && <option value="">Cargando activos…</option>}
            {view === 'empty' && <option value="">No hay activos en el inventario</option>}
            {view === 'data' && <option value="">Elige un activo…</option>}
            {view === 'data' &&
              assets.map((asset) => (
                <option key={asset.id} value={String(asset.id)}>
                  {assetOptionLabel(asset)}
                </option>
              ))}
          </select>
          {view === 'loading' && <LoadingSpinner label="Cargando activos" size="sm" />}
        </div>
      )}

      {notice !== null && (
        <Alert variant="info" title="No se ha podido preseleccionar el activo">
          <p>{notice}</p>
        </Alert>
      )}
      <FieldMessages id={messagesId} messages={messages} />
    </div>
  );
}

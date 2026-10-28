import { useState, type FormEvent } from 'react';

import { Button } from '@/components/ui/button';
import { TableScroll } from '@/components/ui/table-scroll';
import type { RowState } from '@/hooks/use-supplier-directory';
import { renewalInfo } from '@/lib/supplier-renewal';
import type { Supplier, SupplierStatus } from '@/types/suppliers';

import { formatDateTime, formatRate } from './format';
import { RenewalCell, StatusBadge } from './supplier-badges';
import { SupplierError } from './supplier-error';

export interface SupplierTableProps {
  suppliers: readonly Supplier[];
  rows: Readonly<Record<number, RowState>>;
  today: Date;
  onUpdateRate: (id: number, rateInput: string) => void;
  onUpdateStatus: (id: number, status: SupplierStatus) => void;
  onDismissRowError: (id: number) => void;
}

// Sin botón de eliminar: los proveedores se suspenden, no se borran
// (docs/ligthweight-storage-api.md, "Suspensión controlada"; SPECS §10).
export function SupplierTable({ suppliers, rows, today, onUpdateRate, onUpdateStatus, onDismissRowError }: SupplierTableProps) {
  return (
    <TableScroll framed>
      <table className="w-full min-w-[46rem] border-collapse text-left text-sm">
        <caption className="sr-only">Directorio de proveedores</caption>
        <thead className="border-b border-border bg-canvas text-xs uppercase tracking-wide text-ink-muted">
          <tr>
            <th scope="col" className="px-3 py-2 font-semibold">Proveedor</th>
            <th scope="col" className="px-3 py-2 font-semibold">País</th>
            <th scope="col" className="px-3 py-2 font-semibold">Categorías</th>
            <th scope="col" className="px-3 py-2 font-semibold">Tarifa mensual</th>
            <th scope="col" className="px-3 py-2 font-semibold">Renovación</th>
            <th scope="col" className="px-3 py-2 font-semibold">Estado</th>
          </tr>
        </thead>
        <tbody>
          {suppliers.map((supplier) => (
            <SupplierRow
              key={supplier.id}
              supplier={supplier}
              row={rows[supplier.id]}
              today={today}
              onUpdateRate={onUpdateRate}
              onUpdateStatus={onUpdateStatus}
              onDismissRowError={onDismissRowError}
            />
          ))}
        </tbody>
      </table>
    </TableScroll>
  );
}

interface SupplierRowProps {
  supplier: Supplier;
  row: RowState | undefined;
  today: Date;
  onUpdateRate: (id: number, rateInput: string) => void;
  onUpdateStatus: (id: number, status: SupplierStatus) => void;
  onDismissRowError: (id: number) => void;
}

function SupplierRow({ supplier, row, today, onUpdateRate, onUpdateStatus, onDismissRowError }: SupplierRowProps) {
  const isSuspended = supplier.status === 'suspended';
  const isSaving = row?.status === 'saving';
  const renewal = renewalInfo(supplier.contract_renewal_date, today);
  const nextStatus: SupplierStatus = isSuspended ? 'active' : 'suspended';

  return (
    <>
      <tr
        className={`border-b border-border align-top last:border-b-0 ${isSuspended ? 'bg-canvas text-ink-muted' : ''} ${
          renewal.kind === 'upcoming' ? 'border-l-4 border-l-warning-ink' : ''
        }`}
      >
        <th scope="row" className="px-3 py-3 font-normal">
          <span className={`block font-semibold ${isSuspended ? 'text-ink-muted' : 'text-ink'}`}>
            {supplier.name}
          </span>
          {supplier.contact_email !== null && <span className="block text-xs text-ink-muted">{supplier.contact_email}</span>}
          {supplier.notes !== null && <span className="mt-1 block max-w-[14rem] text-xs text-ink-muted">{supplier.notes}</span>}
        </th>
        <td className="px-3 py-3">{supplier.country}</td>
        <td className="px-3 py-3">
          <ul className="flex flex-wrap gap-1">
            {supplier.categories.map((category) => (
              <li key={category} className="rounded-control bg-canvas px-1.5 py-0.5 font-mono text-xs text-ink">
                {category}
              </li>
            ))}
          </ul>
        </td>
        <td className="px-3 py-3">
          {/* key: al cambiar la tarifa (nuevo updated_at) el editor se reinicia cerrado. */}
          <RateCell
            key={supplier.updated_at}
            supplier={supplier}
            isSaving={isSaving && row?.action === 'rate'}
            disabled={isSaving}
            onSubmit={(value) => onUpdateRate(supplier.id, value)}
          />
        </td>
        <td className="px-3 py-3">
          <RenewalCell date={supplier.contract_renewal_date} info={renewal} />
        </td>
        <td className="px-3 py-3">
          <div className="flex flex-col items-start gap-2">
            <StatusBadge status={supplier.status} />
            <Button
              variant="secondary"
              className="px-2 py-1 text-xs"
              isLoading={isSaving && row?.action === 'status'}
              disabled={isSaving}
              aria-label={`${isSuspended ? 'Activar' : 'Suspender'} ${supplier.name}`}
              onClick={() => onUpdateStatus(supplier.id, nextStatus)}
            >
              {isSuspended ? 'Activar' : 'Suspender'}
            </Button>
          </div>
        </td>
      </tr>
      {row?.status === 'error' && (
        <tr className="border-b border-border">
          <td colSpan={6} className="px-3 pb-3">
            <div className="flex flex-col gap-2 pt-2">
              <SupplierError error={row.error} />
              <div>
                <Button variant="secondary" className="px-2 py-1 text-xs" onClick={() => onDismissRowError(supplier.id)}>
                  Cerrar aviso de {supplier.name}
                </Button>
              </div>
            </div>
          </td>
        </tr>
      )}
    </>
  );
}

interface RateCellProps {
  supplier: Supplier;
  isSaving: boolean;
  disabled: boolean;
  onSubmit: (value: string) => void;
}

function RateCell({ supplier, isSaving, disabled, onSubmit }: RateCellProps) {
  const [editing, setEditing] = useState(false);
  const [value, setValue] = useState(String(supplier.monthly_rate));
  const inputId = `rate-${supplier.id}`;

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    onSubmit(value);
  }

  return (
    <div className="flex flex-col gap-1">
      <span className="font-semibold tabular-nums text-ink">{formatRate(supplier.monthly_rate, supplier.currency)}</span>
      <span className="text-xs text-ink-muted">
        Actualizada: <time dateTime={supplier.updated_at}>{formatDateTime(supplier.updated_at)}</time>
      </span>
      {editing ? (
        <form onSubmit={handleSubmit} noValidate className="mt-1 flex flex-wrap items-center gap-1">
          <label htmlFor={inputId} className="sr-only">
            Nueva tarifa mensual de {supplier.name} ({supplier.currency})
          </label>
          <input
            id={inputId}
            inputMode="decimal"
            autoComplete="off"
            value={value}
            onChange={(event) => setValue(event.target.value)}
            className="w-24 rounded-control border border-border bg-surface px-2 py-1 text-sm text-ink outline-none focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand"
          />
          <span className="text-xs text-ink-muted">{supplier.currency}</span>
          <Button type="submit" className="px-2 py-1 text-xs" isLoading={isSaving} disabled={disabled}>
            Guardar
          </Button>
          <Button variant="secondary" className="px-2 py-1 text-xs" disabled={disabled} onClick={() => setEditing(false)}>
            Cancelar
          </Button>
        </form>
      ) : (
        <Button
          variant="secondary"
          className="mt-1 w-fit px-2 py-1 text-xs"
          disabled={disabled}
          aria-label={`Cambiar tarifa de ${supplier.name}`}
          onClick={() => setEditing(true)}
        >
          Cambiar tarifa
        </Button>
      )}
    </div>
  );
}

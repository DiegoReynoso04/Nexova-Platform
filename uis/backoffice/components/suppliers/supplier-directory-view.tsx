'use client';

// Vista de /suppliers: conecta el hook con componentes presentacionales.
// No hace HTTP: todo pasa por useSupplierDirectory → services/suppliers.service.ts.
// No hay botón de eliminar (suspensión controlada; services/api/SPECS.md §10).

import { useState } from 'react';

import { Alert } from '@/components/ui/alert';
import { Button } from '@/components/ui/button';
import { LoadingSpinner } from '@/components/ui/loading-spinner';
import { useSupplierDirectory } from '@/hooks/use-supplier-directory';
import { RENEWAL_WINDOW_DAYS, renewalInfo } from '@/lib/supplier-renewal';

import { SupplierCreateForm } from './supplier-create-form';
import { SupplierError } from './supplier-error';
import { SupplierFilterBar } from './supplier-filters';
import { SupplierTable } from './supplier-table';

export function SupplierDirectoryView() {
  const directory = useSupplierDirectory();
  const { suppliers, filters, list, create, rows, loaded } = directory;
  // Fecha local fijada al montar: referencia para "renueva en los próximos 60 días".
  const [today] = useState(() => new Date());
  const [formOpen, setFormOpen] = useState(false);

  const isLoading = list.status === 'loading';
  const activeCount = suppliers.filter((supplier) => supplier.status === 'active').length;
  const upcomingCount = suppliers.filter(
    (supplier) => renewalInfo(supplier.contract_renewal_date, today).kind === 'upcoming'
  ).length;
  const showForm = formOpen && create.status !== 'success';

  function openForm() {
    directory.resetCreate();
    setFormOpen(true);
  }

  function closeForm() {
    directory.resetCreate();
    setFormOpen(false);
  }

  let liveMessage = '';
  if (isLoading) liveMessage = 'Cargando proveedores…';
  else if (list.status === 'success') liveMessage = `Proveedores en el listado: ${suppliers.length}.`;
  if (create.status === 'success') liveMessage = `Proveedor ${create.supplier.name} registrado.`;

  return (
    <>
      <p role="status" className="sr-only">
        {liveMessage}
      </p>

      <section aria-labelledby="create-heading" className="rounded-lg border border-border bg-surface p-4 sm:p-6">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <h2 id="create-heading" className="text-base font-semibold text-ink">
            Registrar proveedor
          </h2>
          {!showForm && (
            <Button onClick={openForm} aria-expanded={false} aria-controls="create-form-region">
              Nuevo proveedor
            </Button>
          )}
        </div>
        {create.status === 'success' && (
          <div className="mt-4">
            <Alert variant="info" title={`Proveedor «${create.supplier.name}» registrado`}>
              <p>Ya forma parte del directorio (id {create.supplier.id}).</p>
            </Alert>
          </div>
        )}
        {showForm && (
          <div id="create-form-region" className="mt-4">
            <SupplierCreateForm create={create} onSubmit={directory.submitSupplier} onCancel={closeForm} />
          </div>
        )}
      </section>

      <section aria-labelledby="directory-heading" className="flex flex-col gap-4">
        <div className="flex flex-wrap items-end justify-between gap-4">
          <div className="flex flex-col gap-1">
            <h2 id="directory-heading" className="text-base font-semibold text-ink">
              Directorio
            </h2>
            {loaded && (
              <p className="text-sm text-ink-muted">
                {suppliers.length === 1 ? '1 proveedor' : `${suppliers.length} proveedores`} · {activeCount} active ·{' '}
                {suppliers.length - activeCount} suspended
                {upcomingCount > 0 && ` · ${upcomingCount} con renovación en los próximos ${RENEWAL_WINDOW_DAYS} días`}
              </p>
            )}
          </div>
          <SupplierFilterBar filters={filters} onChange={directory.setFilters} />
        </div>

        {list.status === 'error' && (
          <div className="flex flex-col gap-2">
            <SupplierError error={list.error} />
            <div>
              <Button variant="secondary" onClick={directory.reload}>
                Reintentar
              </Button>
            </div>
            {loaded && <p className="text-xs text-ink-muted">Se sigue mostrando el último listado recibido.</p>}
          </div>
        )}

        {!loaded && isLoading && (
          <div className="flex items-center gap-3 rounded-lg border border-dashed border-border bg-surface p-6">
            <LoadingSpinner />
            <span className="text-sm text-ink-muted">Cargando proveedores…</span>
          </div>
        )}

        {loaded && (
          <div className={`flex flex-col gap-2 ${isLoading ? 'opacity-60' : ''}`} aria-busy={isLoading}>
            {suppliers.length === 0 ? (
              <p className="rounded-lg border border-dashed border-border bg-surface p-6 text-center text-sm text-ink-muted">
                {filters.country !== null || filters.category !== null
                  ? 'Ningún proveedor coincide con los filtros.'
                  : 'El directorio está vacío. Pide al equipo técnico que cargue los proveedores iniciales.'}
              </p>
            ) : (
              <SupplierTable
                suppliers={suppliers}
                rows={rows}
                today={today}
                onUpdateRate={directory.updateRate}
                onUpdateStatus={directory.updateStatus}
                onDismissRowError={directory.clearRow}
              />
            )}
          </div>
        )}
      </section>
    </>
  );
}

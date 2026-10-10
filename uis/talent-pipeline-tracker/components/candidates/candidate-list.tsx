'use client';

import { useState } from 'react';
import { useRecords } from '@/hooks/use-records';
import { describeApiError } from '@/lib/api-client';
import { Button } from '@/components/ui/button';
import { LoadingSpinner } from '@/components/ui/loading-spinner';
import { Modal } from '@/components/ui/modal';
import { CandidateCard } from './candidate-card';
import { CandidateFilters } from './candidate-filters';
import { CandidateForm } from './candidate-form';
import { CandidatePagination } from './candidate-pagination';
import { CandidateTable } from './candidate-table';

// Orquestador: consume use-records, no llama a la API directamente. Tres
// estados visuales distintos (cargando / error con reintento / vacío) más
// el éxito con tabla (escritorio) + tarjetas (móvil) y paginación. La
// creación de candidaturas (REQ-4) vive en un modal para no salir del
// listado; candidate-form.tsx no sabe nada de cómo se presenta y ya avisa
// del resultado por el toast (REQ-4/REQ-5), así que aquí solo hace falta
// cerrar el modal y refrescar la lista.
export function CandidateList() {
  const {
    records,
    total,
    page,
    limit,
    status,
    error,
    refetch,
    statusFilter,
    setStatusFilter,
    stageFilter,
    setStageFilter,
    search,
    setSearch,
    setPage,
    hasNextPage,
    hasPreviousPage,
  } = useRecords();

  const [isCreateOpen, setIsCreateOpen] = useState(false);
  // El <dialog> de components/ui/modal.tsx no desmonta su contenido al cerrarse:
  // cada apertura monta un formulario nuevo (key) para que no arrastre el
  // estado del intento anterior (errores ni el bloqueo de reenvío tras un
  // guardado ilegible, lib/submit-error.ts).
  const [createFormKey, setCreateFormKey] = useState(0);

  function openCreate() {
    setCreateFormKey((key) => key + 1);
    setIsCreateOpen(true);
  }

  function handleCreateSuccess() {
    setIsCreateOpen(false);
    refetch();
  }

  return (
    <section aria-labelledby="candidates-heading" className="flex flex-col gap-6">
      <header className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h1 id="candidates-heading" className="text-xl font-semibold text-ink">
            Candidaturas
          </h1>
          <p className="text-sm text-ink-muted">Asistente de Dirección · Sede de Valencia</p>
        </div>
        <Button onClick={openCreate}>Nueva candidatura</Button>
      </header>

      <CandidateFilters
        statusFilter={statusFilter}
        onStatusFilterChange={setStatusFilter}
        stageFilter={stageFilter}
        onStageFilterChange={setStageFilter}
        search={search}
        onSearchChange={setSearch}
      />

      {status === 'loading' && (
        <div
          role="status"
          className="flex items-center justify-center rounded-control border border-border bg-surface p-10"
        >
          <LoadingSpinner label="Cargando candidaturas…" />
        </div>
      )}

      {status === 'error' && (
        <div
          role="alert"
          className="flex flex-col items-start gap-3 rounded-control border border-danger-ink/20 bg-danger-surface p-6 text-danger-ink"
        >
          <p className="text-sm">
            No se pudieron cargar las candidaturas.
            {error ? ` ${describeApiError(error)}` : ''}
          </p>
          <Button variant="secondary" onClick={refetch}>
            Reintentar
          </Button>
        </div>
      )}

      {status === 'empty' && (
        <div
          role="status"
          className="rounded-control border border-border bg-surface p-10 text-center text-sm text-ink-muted"
        >
          No se encontraron candidaturas con estos filtros.
        </div>
      )}

      {status === 'success' && (
        <>
          <CandidateTable records={records} />
          <ul className="flex flex-col gap-3 md:hidden">
            {records.map((record) => (
              <CandidateCard key={record.id} record={record} />
            ))}
          </ul>
          <CandidatePagination
            page={page}
            limit={limit}
            total={total}
            hasNextPage={hasNextPage}
            hasPreviousPage={hasPreviousPage}
            onPageChange={setPage}
          />
        </>
      )}

      <Modal open={isCreateOpen} title="Nueva candidatura" onClose={() => setIsCreateOpen(false)}>
        <CandidateForm
          key={createFormKey}
          mode={{ kind: 'create' }}
          onSuccess={handleCreateSuccess}
          onCancel={() => setIsCreateOpen(false)}
        />
      </Modal>
    </section>
  );
}

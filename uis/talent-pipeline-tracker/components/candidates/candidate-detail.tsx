'use client';

import { useState } from 'react';
import Link from 'next/link';
import { notFound } from 'next/navigation';
import { useRecordDetail } from '@/hooks/use-record-detail';
import { describeApiError } from '@/lib/api-client';
import { Button } from '@/components/ui/button';
import { LoadingSpinner } from '@/components/ui/loading-spinner';
import { Modal } from '@/components/ui/modal';
import { CandidateForm } from './candidate-form';
import { NotesList } from '@/components/notes/notes-list';
import { CandidateStatusControls } from './candidate-status-controls';
import { formatDate, toSafeHttpUrl } from '@/lib/format';

export interface CandidateDetailProps {
  id: string;
}

const LINK_CLASSES =
  'text-brand underline-offset-2 outline-none hover:underline focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand';

// Orquestador de solo lectura + edición (REQ-3/REQ-4): consume
// use-record-detail, no llama a la API directamente. La edición de datos
// personales/profesionales vive en un modal con candidate-form.tsx (PUT);
// status/stage se editan con candidate-status-controls.tsx (PATCH,
// optimista). Las notas todavía no viven en este componente.
export function CandidateDetail({ id }: CandidateDetailProps) {
  const { status, record, error, refetch } = useRecordDetail(id);
  const [isEditOpen, setIsEditOpen] = useState(false);
  // El <dialog> de components/ui/modal.tsx no desmonta su contenido al cerrarse:
  // cada apertura monta un formulario nuevo (key) para que no arrastre el
  // estado del intento anterior (errores ni el bloqueo de reenvío tras un
  // guardado ilegible, lib/submit-error.ts).
  const [editFormKey, setEditFormKey] = useState(0);

  function openEdit() {
    setEditFormKey((key) => key + 1);
    setIsEditOpen(true);
  }

  // notFound() se invoca aquí, de forma síncrona durante el render: el hook
  // deliberadamente no lo hace (ver comentario en use-record-detail.ts).
  if (status === 'not-found') {
    notFound();
  }

  if (status === 'loading') {
    return (
      <div
        role="status"
        className="flex items-center justify-center rounded-control border border-border bg-surface p-10"
      >
        <LoadingSpinner label="Cargando candidatura…" />
      </div>
    );
  }

  if (status === 'error') {
    return (
      <div
        role="alert"
        className="flex flex-col items-start gap-3 rounded-control border border-danger-ink/20 bg-danger-surface p-6 text-danger-ink"
      >
        <p className="text-sm">
          No se pudo cargar la candidatura.
          {error ? ` ${describeApiError(error)}` : ''}
        </p>
        <Button variant="secondary" onClick={refetch}>
          Reintentar
        </Button>
      </div>
    );
  }

  if (!record) return null;

  // candidate-form.tsx ya avisa del resultado por el toast (REQ-4/REQ-5);
  // aquí solo hace falta cerrar el modal y refrescar los datos.
  function handleEditSuccess() {
    setIsEditOpen(false);
    refetch();
  }

  // El PATCH ya devuelve el RecordOut fresco (incluido updated_at); las
  // dos selects de candidate-status-controls.tsx ya se actualizan solas y
  // de forma optimista, así que aquí solo hace falta refrescar el resto
  // de la vista (p. ej. "Última actualización" en el <dl>).
  function handleStatusUpdated() {
    refetch();
  }

  return (
    <article className="flex flex-col gap-6">
      <header className="flex flex-wrap items-center justify-between gap-3">
        <h1 className="text-xl font-semibold text-ink">{record.full_name}</h1>
        <Button variant="secondary" onClick={openEdit}>
          Editar
        </Button>
      </header>

      <CandidateStatusControls
        id={record.id}
        status={record.status}
        stage={record.stage}
        onUpdated={handleStatusUpdated}
      />

      <dl className="grid grid-cols-1 gap-x-6 gap-y-4 rounded-control border border-border bg-surface p-6 sm:grid-cols-2">
        <DetailRow label="Puesto" value={record.position} />
        <DetailRow label="Email" value={record.email} />
        <DetailRow label="Teléfono" value={record.phone} />
        <DetailRow label="Años de experiencia" value={String(record.experience_years)} />
        <DetailRow label="Fecha de aplicación" value={formatDate(record.applied_at)} />
        <DetailRow label="Última actualización" value={formatDate(record.updated_at)} />
        <LinkOrText label="LinkedIn" url={record.linkedin_url} />
        <LinkOrText label="CV" url={record.cv_url} />
      </dl>

      <NotesList recordId={record.id} />

      <p className="text-xs text-ink-muted">ID: {record.id}</p>

      <Link href="/" className={`text-sm ${LINK_CLASSES}`}>
        ← Volver al listado
      </Link>

      <Modal open={isEditOpen} title="Editar candidatura" onClose={() => setIsEditOpen(false)}>
        <CandidateForm
          key={editFormKey}
          mode={{ kind: 'edit', id: record.id, initialValues: record }}
          onSuccess={handleEditSuccess}
          onCancel={() => setIsEditOpen(false)}
        />
      </Modal>
    </article>
  );
}

function DetailRow({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <dt className="text-sm text-ink-muted">{label}</dt>
      <dd className="text-sm text-ink">{value}</dd>
    </div>
  );
}

// linkedin_url/cv_url pueden ser null o texto que no es una URL válida
// (§4.2). Solo se enlaza tras validar http(s); si no, texto plano o un
// marcador neutro cuando no hay valor.
function LinkOrText({ label, url }: { label: string; url: string | null }) {
  const safeUrl = toSafeHttpUrl(url);

  return (
    <div>
      <dt className="text-sm text-ink-muted">{label}</dt>
      <dd className="text-sm text-ink">
        {safeUrl ? (
          <a href={safeUrl} target="_blank" rel="noreferrer noopener" className={LINK_CLASSES}>
            {safeUrl}
          </a>
        ) : url ? (
          <span>{url}</span>
        ) : (
          <span className="text-ink-muted">Sin especificar</span>
        )}
      </dd>
    </div>
  );
}

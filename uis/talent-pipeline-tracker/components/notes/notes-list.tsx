'use client';

import { useNotes } from '@/hooks/use-notes';
import { describeApiError } from '@/lib/api-client';
import { Button } from '@/components/ui/button';
import { LoadingSpinner } from '@/components/ui/loading-spinner';
import { useToast } from '@/components/ui/toast-notification';
import { NoteForm } from './note-form';
import { NoteItem } from './note-item';

export interface NotesListProps {
  recordId: string;
}

// Orquestador de notas (REQ-3): consume use-notes, no llama a la API
// directamente. `notesCount` reconciliado: siempre desde esta lista en
// memoria (equivalente a meta.total tras cada mutación), nunca desde el
// notes_count original de RecordOut, que queda obsoleto.
export function NotesList({ recordId }: NotesListProps) {
  const {
    notes,
    notesCount,
    status,
    error,
    refetch,
    isAddingNote,
    addNoteError,
    addNote,
    deletingNoteId,
    deleteNote,
  } = useNotes(recordId);

  const { notifySuccess, notifyError } = useToast();

  // addNote/deleteNote del hook solo devuelven boolean: el toast se basa
  // únicamente en ese resultado (no en el estado de error del hook leído
  // tras el await, que quedaría obsoleto por el cierre de esta función).
  // El detalle del fallo de alta ya se muestra en línea en note-form.tsx
  // vía addNoteError, que sí es una lectura fresca en cada render.
  async function handleAddNote(content: string) {
    const ok = await addNote(content);
    if (ok) notifySuccess('Nota añadida.');
    else notifyError('No se pudo añadir la nota.');
    return ok;
  }

  async function handleDeleteNote(noteId: string) {
    const ok = await deleteNote(noteId);
    if (ok) notifySuccess('Nota eliminada.');
    else notifyError('No se pudo eliminar la nota.');
    return ok;
  }

  return (
    <section aria-labelledby="notes-heading" className="flex flex-col gap-4">
      <h2 id="notes-heading" className="text-base font-semibold text-ink">
        Notas ({notesCount})
      </h2>

      {status === 'loading' && (
        <div
          role="status"
          className="flex items-center justify-center rounded-control border border-border bg-surface p-6"
        >
          <LoadingSpinner label="Cargando notas…" />
        </div>
      )}

      {status === 'error' && (
        <div
          role="alert"
          className="flex flex-col items-start gap-3 rounded-control border border-danger-ink/20 bg-danger-surface p-4 text-danger-ink"
        >
          <p className="text-sm">
            No se pudieron cargar las notas.
            {error ? ` ${describeApiError(error)}` : ''}
          </p>
          <Button variant="secondary" onClick={refetch}>
            Reintentar
          </Button>
        </div>
      )}

      {status === 'success' && (
        <>
          {notes.length === 0 ? (
            <p className="text-sm text-ink-muted">Sin notas todavía.</p>
          ) : (
            <ul className="flex flex-col gap-3">
              {notes.map((note) => (
                <NoteItem
                  key={note.id}
                  note={note}
                  onDelete={handleDeleteNote}
                  isDeleting={deletingNoteId === note.id}
                  isDeleteBlocked={deletingNoteId !== null}
                />
              ))}
            </ul>
          )}

          <NoteForm onSubmit={handleAddNote} isSubmitting={isAddingNote} error={addNoteError} />
        </>
      )}
    </section>
  );
}

// Notas de un registro: carga inicial + mutaciones con feedback inmediato,
// sin recargar la lista completa (REQ-3, REQ-5). `notesCount` es siempre la
// longitud de esta lista en memoria, nunca el `notes_count` de RecordOut
// (queda obsoleto tras crear/eliminar una nota).

import { useCallback, useEffect, useRef, useState } from 'react';
import { asError } from '@/lib/api-client';
import { addNote as addNoteRequest, deleteNote as deleteNoteRequest, getNotes } from '@/services/notes.service';
import type { Note } from '@/types/record';

export type NotesStatus = 'loading' | 'success' | 'error';

interface NotesState {
  status: NotesStatus;
  notes: Note[];
  error: Error | null;
}

export interface UseNotesResult {
  notes: Note[];
  notesCount: number;
  status: NotesStatus;
  error: Error | null;
  refetch: () => void;

  isAddingNote: boolean;
  addNoteError: Error | null;
  addNote: (content: string) => Promise<boolean>;

  deletingNoteId: string | null;
  deleteNoteError: Error | null;
  deleteNote: (noteId: string) => Promise<boolean>;
}

export function useNotes(recordId: string): UseNotesResult {
  const [state, setState] = useState<NotesState>({
    status: 'loading',
    notes: [],
    error: null,
  });

  const latestRequestId = useRef(0);

  const fetchNotes = useCallback(() => {
    const requestId = ++latestRequestId.current;
    setState((prev) => ({ ...prev, status: 'loading', error: null }));

    getNotes(recordId)
      .then((response) => {
        if (latestRequestId.current !== requestId) return;
        setState({ status: 'success', notes: response.data, error: null });
      })
      .catch((error: unknown) => {
        if (latestRequestId.current !== requestId) return;
        setState((prev) => ({
          ...prev,
          status: 'error',
          error: asError(error),
        }));
      });
  }, [recordId]);

  useEffect(() => {
    fetchNotes();
  }, [fetchNotes]);

  const [isAddingNote, setIsAddingNote] = useState(false);
  const [addNoteError, setAddNoteError] = useState<Error | null>(null);

  const addNote = useCallback(
    async (content: string): Promise<boolean> => {
      if (isAddingNote) return false; // evita envíos duplicados (REQ-5)

      setIsAddingNote(true);
      setAddNoteError(null);

      try {
        const created = await addNoteRequest(recordId, { content });
        setState((prev) => ({ ...prev, notes: [...prev.notes, created] }));
        return true;
      } catch (error) {
        setAddNoteError(asError(error));
        return false;
      } finally {
        setIsAddingNote(false);
      }
    },
    [recordId, isAddingNote]
  );

  const [deletingNoteId, setDeletingNoteId] = useState<string | null>(null);
  const [deleteNoteError, setDeleteNoteError] = useState<Error | null>(null);

  const deleteNote = useCallback(
    async (noteId: string): Promise<boolean> => {
      if (deletingNoteId !== null) return false; // evita envíos duplicados (REQ-5)

      setDeletingNoteId(noteId);
      setDeleteNoteError(null);

      try {
        await deleteNoteRequest(recordId, noteId);
        setState((prev) => ({ ...prev, notes: prev.notes.filter((note) => note.id !== noteId) }));
        return true;
      } catch (error) {
        setDeleteNoteError(asError(error));
        return false;
      } finally {
        setDeletingNoteId(null);
      }
    },
    [recordId, deletingNoteId]
  );

  return {
    notes: state.notes,
    notesCount: state.notes.length,
    status: state.status,
    error: state.error,
    refetch: fetchNotes,
    isAddingNote,
    addNoteError,
    addNote,
    deletingNoteId,
    deleteNoteError,
    deleteNote,
  };
}

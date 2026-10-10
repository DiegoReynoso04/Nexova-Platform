// Obtiene un registro por id (REQ-1, REQ-3). Distingue 404 de un error
// genérico (§5.4). El hook NO llama a next/navigation.notFound(): esa
// llamada debe hacerse de forma síncrona en el render del componente de
// página al ver status === 'not-found', nunca dentro de un callback async.

import { useCallback, useEffect, useRef, useState } from 'react';
import { NotFoundError, asError } from '@/lib/api-client';
import { getRecordById } from '@/services/records.service';
import type { RecordListItem } from '@/types/record';

export type RecordDetailStatus = 'loading' | 'success' | 'not-found' | 'error';

interface RecordDetailState {
  status: RecordDetailStatus;
  record: RecordListItem | null;
  error: Error | null;
}

export interface UseRecordDetailResult extends RecordDetailState {
  refetch: () => void;
}

export function useRecordDetail(id: string): UseRecordDetailResult {
  const [state, setState] = useState<RecordDetailState>({
    status: 'loading',
    record: null,
    error: null,
  });

  // Descarta la respuesta si ya hay una petición más reciente en curso
  // (id cambiado o refetch posterior).
  const latestRequestId = useRef(0);

  const fetchRecord = useCallback(() => {
    const requestId = ++latestRequestId.current;
    setState((prev) => ({ ...prev, status: 'loading', error: null }));

    getRecordById(id)
      .then((record) => {
        if (latestRequestId.current !== requestId) return;
        setState({ status: 'success', record, error: null });
      })
      .catch((error: unknown) => {
        if (latestRequestId.current !== requestId) return;
        if (error instanceof NotFoundError) {
          setState({ status: 'not-found', record: null, error: null });
          return;
        }
        setState({
          status: 'error',
          record: null,
          error: asError(error),
        });
      });
  }, [id]);

  useEffect(() => {
    fetchRecord();
  }, [fetchRecord]);

  return { ...state, refetch: fetchRecord };
}

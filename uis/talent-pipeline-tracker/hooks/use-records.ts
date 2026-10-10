// Listado de candidaturas: filtros, búsqueda con debounce, paginación y
// estados de carga/vacío/error diferenciados (REQ-2). Cambiar cualquier
// filtro o el término de búsqueda reinicia `page` a 1. Las respuestas de
// peticiones ya obsoletas se descartan (control de condiciones de carrera).

import { useCallback, useEffect, useRef, useState } from 'react';
import { useDebounce } from '@/hooks/use-debounce';
import { asError } from '@/lib/api-client';
import { getRecords } from '@/services/records.service';
import type { KnownStage, KnownStatus, RecordListItem } from '@/types/record';

export type RecordsListStatus = 'loading' | 'success' | 'empty' | 'error';

const DEFAULT_LIMIT = 20;
const SEARCH_DEBOUNCE_MS = 300;

interface RecordsState {
  status: RecordsListStatus;
  records: RecordListItem[];
  total: number;
  error: Error | null;
}

export interface UseRecordsResult {
  records: RecordListItem[];
  total: number;
  page: number;
  limit: number;
  status: RecordsListStatus;
  error: Error | null;
  refetch: () => void;

  statusFilter: KnownStatus | '';
  setStatusFilter: (status: KnownStatus | '') => void;
  stageFilter: KnownStage | '';
  setStageFilter: (stage: KnownStage | '') => void;
  search: string;
  setSearch: (value: string) => void;

  setPage: (page: number) => void;
  hasNextPage: boolean;
  hasPreviousPage: boolean;
}

export function useRecords(limit: number = DEFAULT_LIMIT): UseRecordsResult {
  const [page, setPageRaw] = useState(1);
  const setPage = useCallback((nextPage: number) => {
    setPageRaw(Math.max(1, nextPage));
  }, []);

  const [statusFilter, setStatusFilterRaw] = useState<KnownStatus | ''>('');
  const setStatusFilter = useCallback(
    (value: KnownStatus | '') => {
      setStatusFilterRaw(value);
      setPage(1); // REQ-2: cambiar un filtro reinicia la página
    },
    [setPage]
  );

  const [stageFilter, setStageFilterRaw] = useState<KnownStage | ''>('');
  const setStageFilter = useCallback(
    (value: KnownStage | '') => {
      setStageFilterRaw(value);
      setPage(1);
    },
    [setPage]
  );

  const [search, setSearch] = useState('');
  const debouncedSearch = useDebounce(search, SEARCH_DEBOUNCE_MS);

  // El término debounced cambia de forma asíncrona (no vía un setter propio
  // que podamos combinar con setPage), así que su reinicio de página va en
  // un efecto separado.
  useEffect(() => {
    setPage(1);
  }, [debouncedSearch, setPage]);

  const [state, setState] = useState<RecordsState>({
    status: 'loading',
    records: [],
    total: 0,
    error: null,
  });

  const latestRequestId = useRef(0);

  const fetchRecords = useCallback(() => {
    const requestId = ++latestRequestId.current;
    setState((prev) => ({ ...prev, status: 'loading', error: null }));

    getRecords({ status: statusFilter, stage: stageFilter, search: debouncedSearch, page, limit })
      .then((result) => {
        if (latestRequestId.current !== requestId) return; // respuesta obsoleta
        setState({
          status: result.data.length === 0 ? 'empty' : 'success',
          records: result.data,
          total: result.total,
          error: null,
        });
      })
      .catch((error: unknown) => {
        if (latestRequestId.current !== requestId) return;
        setState((prev) => ({
          ...prev,
          status: 'error',
          error: asError(error),
        }));
      });
  }, [statusFilter, stageFilter, debouncedSearch, page, limit]);

  useEffect(() => {
    fetchRecords();
  }, [fetchRecords]);

  return {
    records: state.records,
    total: state.total,
    page,
    limit,
    status: state.status,
    error: state.error,
    refetch: fetchRecords,

    statusFilter,
    setStatusFilter,
    stageFilter,
    setStageFilter,
    search,
    setSearch,

    setPage,
    hasNextPage: page * limit < state.total,
    hasPreviousPage: page > 1,
  };
}

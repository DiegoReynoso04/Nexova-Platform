import type { AnalysisResult } from '@/types/incidents';

import { DistributionTable } from './distribution-table';
import { InvalidBreakdownTable } from './invalid-breakdown-table';
import { SatisfactionPanel } from './satisfaction-panel';
import { TotalsCards } from './totals-cards';

export interface IncidentResultsProps {
  result: AnalysisResult;
}

// Métricas de un análisis. La vista las carga con next/dynamic en un único
// chunk (docs/caching-analysis.md, D6): solo existen después de analizar un
// CSV. Devuelve un fragmento para quedar dentro de la misma sección (y del
// mismo `gap`) que antes de la carga diferida.
export function IncidentResults({ result }: IncidentResultsProps) {
  return (
    <>
      <TotalsCards totals={result.totals} />
      <InvalidBreakdownTable items={result.invalid_breakdown} />
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <DistributionTable
          headingId="categories-heading"
          title="Categorías"
          codeLabel="Categoría"
          items={result.categories}
          note="Registros válidos por categoría; porcentaje sobre registros válidos."
        />
        <DistributionTable
          headingId="statuses-heading"
          title="Estados"
          codeLabel="Estado"
          items={result.statuses}
          note="Registros válidos por estado; porcentaje sobre registros válidos."
        />
      </div>
      <SatisfactionPanel satisfaction={result.satisfaction} />
    </>
  );
}

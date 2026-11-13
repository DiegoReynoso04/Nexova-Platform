import type { Metadata } from 'next';

import { WeeklyPerformanceView } from '@/components/reporting/weekly-performance-view';

// Server Component: exporta la metadata y renderiza la vista interactiva.
export const metadata: Metadata = {
  title: 'Reporte semanal · Nexova',
  description:
    'Reporte semanal de desempeño por oficina y programa: costo de material, kits entregados, escasez y variación de costo de Valencia y Miami.',
};

export default function ReportingPage() {
  return (
    <>
      <div className="flex flex-col gap-2">
        <h1 className="text-lg font-semibold text-ink">Reporte semanal de desempeño por oficina y programa</h1>
        <p className="text-sm text-ink-muted">
          Cuánto se invierte en material de formación, cuántos kits se entregan y cuántas veces falta stock o sube el
          costo, en Valencia y en Miami, semana a semana.
        </p>
      </div>
      <WeeklyPerformanceView />
    </>
  );
}

import { Button } from '@/components/ui/button';
import { weekPeriodLabel } from '@/lib/reporting-format';

export interface WeekPickerProps {
  /** El lunes de la semana mostrada; `null` mientras se busca la última calculada. */
  week: string | null;
  /** `null` desactiva el botón. */
  previous: string | null;
  next: string | null;
  onGoToWeek: (week: string) => void;
}

// Encabezado del reporte: el período (lunes a domingo, UTC) y el paso a la semana anterior o
// siguiente. «Siguiente» se desactiva en la última semana calculada.
export function WeekPicker({ week, previous, next, onGoToWeek }: WeekPickerProps) {
  return (
    <div className="flex flex-col gap-3 rounded-lg border border-border bg-surface px-4 py-3 sm:flex-row sm:items-center sm:justify-between">
      <div className="min-w-0">
        <p aria-live="polite" className="text-base font-semibold text-ink">
          {week === null ? 'Buscando la última semana calculada…' : weekPeriodLabel(week)}
        </p>
        <p className="text-xs text-ink-muted">Las semanas se cuentan de lunes a domingo, en horario UTC.</p>
      </div>
      <div className="flex flex-wrap gap-2 sm:shrink-0 sm:flex-nowrap">
        <Button variant="secondary" disabled={previous === null} onClick={() => previous !== null && onGoToWeek(previous)}>
          ← Semana anterior
        </Button>
        <Button variant="secondary" disabled={next === null} onClick={() => next !== null && onGoToWeek(next)}>
          Semana siguiente →
        </Button>
      </div>
    </div>
  );
}

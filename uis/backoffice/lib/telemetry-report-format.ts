// Presentación del reporte técnico (/telemetry). Módulo puro: lo usan la vista y
// los tests. La API no redondea (SPECS §48): aquí se formatean las tasas, y el
// valor exacto queda en la respuesta.

import type { ErrorClass, EventsPerDayRow } from '@/types/telemetry-report';

const PERCENT = new Intl.NumberFormat('es-ES', { style: 'percent', maximumFractionDigits: 1 });
const MILLISECONDS = new Intl.NumberFormat('es-ES', { maximumFractionDigits: 0 });

export const ERROR_CLASS_LABELS: Readonly<Record<ErrorClass, string>> = {
  system: 'Sistema',
  rejected: 'Rechazado',
};

/** `0.0577` → «5,8 %». */
export function formatPercent(ratio: number): string {
  return PERCENT.format(ratio);
}

/** `478.75` → «479 ms». */
export function formatMs(value: number): string {
  return `${MILLISECONDS.format(value)} ms`;
}

/** Fecha local legible del periodo. `timeZone` solo para los tests. */
export function formatPeriodDate(iso: string, timeZone?: string): string {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return iso;
  return new Intl.DateTimeFormat('es-ES', { dateStyle: 'medium', timeStyle: 'short', timeZone }).format(date);
}

export interface DailyVolume {
  day: string;
  /** Eventos por `service`, en el orden en que los da la API. */
  services: readonly { service: string; events: number }[];
  total: number;
  /** Largo de la barra: 0–100, sobre el día con más eventos. */
  barPercent: number;
}

/** Filas de `events_per_day` (día × service) → una por día, con su total. */
export function dailyVolumes(rows: readonly EventsPerDayRow[]): DailyVolume[] {
  const days = new Map<string, { service: string; events: number }[]>();
  for (const { day, service, events } of rows) {
    days.set(day, [...(days.get(day) ?? []), { service, events }]);
  }
  const totals = [...days].map(([day, services]) => ({
    day,
    services,
    total: services.reduce((sum, item) => sum + item.events, 0),
  }));
  const max = Math.max(0, ...totals.map((item) => item.total));
  return totals.map((item) => ({ ...item, barPercent: max === 0 ? 0 : (item.total / max) * 100 }));
}

/** Los `service` de `events_per_day`, en orden de aparición: las columnas de la tabla. */
export function volumeServices(rows: readonly EventsPerDayRow[]): string[] {
  return [...new Set(rows.map((row) => row.service))];
}

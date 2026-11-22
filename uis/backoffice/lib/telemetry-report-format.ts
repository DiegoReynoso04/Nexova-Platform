// Presentación del reporte técnico (/telemetry). Módulo puro: lo usan la vista y
// los tests. La API no redondea (SPECS §48): aquí se formatean las tasas, y el
// valor exacto queda en la respuesta.

import type { ErrorClass, EventsPerDayRow, TelemetryReportUiError } from '@/types/telemetry-report';

export interface CopyText {
  title: string;
  body: string;
}

/** Textos de las dos fases de la tarea mientras no hay reporte (DEV-55, A16). */
export const TASK_PHASE_COPY: Readonly<Record<'queued' | 'computing', CopyText>> = {
  queued: {
    title: 'En cola',
    body: 'El reporte está esperando a que el servidor tenga un hueco para calcularlo. No hace falta recargar la página.',
  },
  computing: {
    title: 'Calculando',
    body: 'El servidor está calculando el reporte. Con muchos eventos puede tardar unos minutos.',
  },
};

/** Texto de cada error: fijo, sin códigos HTTP ni detalles técnicos. */
export function telemetryReportErrorCopy(error: TelemetryReportUiError): CopyText {
  switch (error.kind) {
    case 'queue_unavailable':
      return {
        title: 'El servicio de cálculo no está disponible',
        body: 'No se pudo pedir el reporte ahora mismo. Inténtalo de nuevo en unos minutos.',
      };
    case 'task_failed':
      return {
        title: 'No se pudo calcular el reporte',
        body: 'El cálculo falló tras varios intentos. Inténtalo de nuevo; si vuelve a fallar, avisa al equipo técnico.',
      };
    case 'task_expired':
      return {
        title: 'El reporte ya no está disponible',
        body: 'Ha pasado demasiado tiempo desde que se pidió. Pídelo de nuevo.',
      };
    case 'polling_timeout':
      return {
        title: 'El reporte está tardando demasiado',
        body: 'Sigue sin terminar tras 10 minutos. Inténtalo de nuevo más tarde; si se repite, avisa al equipo técnico.',
      };
    case 'network':
      return {
        title: 'No se pudo conectar con el servidor',
        body: 'Comprueba tu conexión e inténtalo de nuevo. Si el problema continúa, avisa al equipo técnico.',
      };
    case 'timeout':
      return { title: 'La operación tardó demasiado', body: 'El servidor no respondió a tiempo. Inténtalo de nuevo.' };
    case 'server_error':
      return { title: 'Error del servidor', body: 'No se pudo calcular el reporte. Inténtalo de nuevo en unos minutos.' };
    case 'request_invalid':
      return { title: 'La solicitud no es válida', body: 'Inténtalo de nuevo. Si el problema continúa, avisa al equipo técnico.' };
    case 'unexpected_response':
      return {
        title: 'Respuesta inesperada del servidor',
        body: 'La respuesta no tiene el formato esperado, así que no se muestra ningún dato.',
      };
    case 'config':
      return { title: 'La aplicación no está bien configurada', body: 'Avisa al equipo técnico para que la revise.' };
    case 'session_expired':
      return { title: 'La sesión ha caducado', body: 'Vuelve a iniciar sesión para continuar.' };
  }
}

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

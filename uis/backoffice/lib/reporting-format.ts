// Presentación del reporte semanal (/reporting). Módulo puro: lo usan la vista y los tests.
//
// Reglas de negocio que viven aquí, porque son de presentación y las prueba Jest:
// - EUR (Valencia) y USD (Miami) nunca se suman ni se convierten (BRIEFING §7): `officeTotal`
//   lanza `MixedCurrencyError` si recibe más de una moneda.
// - El costo se suma en céntimos enteros: la API devuelve un número JSON (flotante) sin redondear.
// - El centinela `_unassigned` nunca se muestra: «Sin programa asignado».

import {
  CURRENCY_BY_OFFICE,
  REPORT_OFFICES,
  UNASSIGNED_PROGRAMME,
  type Currency,
  type Office,
  type PipelineRun,
  type ReportingUiError,
  type WeeklyPerformanceEntry,
} from '@/types/reporting';

/** Cron semanal (lunes 06:00) más un día de margen: pasado esto, el reporte puede estar desactualizado. */
export const STALE_AFTER_DAYS = 8;

export const OFFICE_LABELS: Readonly<Record<Office, string>> = { valencia: 'Valencia', miami: 'Miami' };
export const UNASSIGNED_LABEL = 'Sin programa asignado';

export const CURRENCY_NOTE =
  'Valencia se expresa en euros y Miami en dólares; las cifras no se suman ni se convierten.';
export const UNASSIGNED_NOTE =
  'El material todavía no está clasificado por programa; por ahora las cifras de cada oficina se muestran juntas.';
export const KITS_NOTE = 'Un kit entregado es una orden de salida, sin importar cuántas unidades lleve.';
export const STALE_NOTICE =
  'Los datos pueden estar desactualizados: no se ha completado ninguna actualización en la última semana.';

// ---------------------------------------------------------------------------
// Los 4 KPI del BRIEFING (§2): nombre y «Qué mide» literales.
// ---------------------------------------------------------------------------

export type KpiKey =
  | 'total_material_cost'
  | 'kits_delivered_count'
  | 'shortage_events_count'
  | 'cost_variance_events_count';

export interface KpiDefinition {
  key: KpiKey;
  title: string;
  question: string;
  kind: 'money' | 'count';
  note?: string;
}

export const KPIS: readonly KpiDefinition[] = [
  {
    key: 'total_material_cost',
    title: 'Costo de material por oficina/programa',
    question:
      'Cuánto gastó una oficina adquiriendo material de formación o incorporación para un programa dado, durante la semana.',
    kind: 'money',
  },
  {
    key: 'kits_delivered_count',
    title: 'Kits entregados',
    question:
      'Cuántos kits o certificados se entregaron realmente a clientes, candidatos, consultores o agentes durante la semana.',
    kind: 'count',
    note: KITS_NOTE,
  },
  {
    key: 'shortage_events_count',
    title: 'Frecuencia de escasez',
    question:
      'Cuántas veces durante la semana el stock de material de un programa cayó por debajo del mínimo configurado.',
    kind: 'count',
  },
  {
    key: 'cost_variance_events_count',
    title: 'Frecuencia de variación de costo',
    question:
      'Cuántas veces durante la semana el costo de un proveedor de material subió de forma anómala respecto a su histórico.',
    kind: 'count',
  },
];

// ---------------------------------------------------------------------------
// Programas, subtotales por oficina y barras
// ---------------------------------------------------------------------------

export function programmeLabel(programmeId: string): string {
  return programmeId === UNASSIGNED_PROGRAMME ? UNASSIGNED_LABEL : programmeId;
}

/** Los programas reales primero, por orden alfabético; «Sin programa asignado» al final. */
export function compareProgrammes(a: string, b: string): number {
  const aUnassigned = a === UNASSIGNED_PROGRAMME;
  const bUnassigned = b === UNASSIGNED_PROGRAMME;
  if (aUnassigned !== bUnassigned) return aUnassigned ? 1 : -1;
  return a.localeCompare(b, 'es');
}

/** Todas las filas son del centinela: todavía no hay clasificación por programa. */
export function allUnassigned(entries: readonly WeeklyPerformanceEntry[]): boolean {
  return entries.length > 0 && entries.every((entry) => entry.programme_id === UNASSIGNED_PROGRAMME);
}

export class MixedCurrencyError extends Error {
  constructor() {
    super('A subtotal cannot mix currencies');
    this.name = 'MixedCurrencyError';
  }
}

function toCents(amount: number): number {
  return Math.round(amount * 100);
}

function entryValue(entry: WeeklyPerformanceEntry, key: KpiKey): number {
  // El costo, redondeado a céntimos: sumar flotantes crudos arrastraría 0,1 + 0,2.
  return key === 'total_material_cost' ? toCents(entry[key]) / 100 : entry[key];
}

/**
 * Subtotal de un KPI para las filas **de una oficina** (sus programas). Lanza `MixedCurrencyError`
 * si las filas no comparten moneda: nunca hay un total entre Valencia y Miami.
 */
export function officeTotal(entries: readonly WeeklyPerformanceEntry[], key: KpiKey): number {
  if (new Set(entries.map((entry) => entry.currency)).size > 1) throw new MixedCurrencyError();
  if (key === 'total_material_cost') return entries.reduce((sum, entry) => sum + toCents(entry[key]), 0) / 100;
  return entries.reduce((sum, entry) => sum + entry[key], 0);
}

export interface OfficeProgramme {
  programmeId: string;
  label: string;
  value: number;
}

export interface OfficeKpi {
  office: Office;
  officeLabel: string;
  currency: Currency;
  /** Sin filas esta semana: «Sin actividad esta semana», no un cero inventado. */
  hasActivity: boolean;
  total: number;
  programmes: readonly OfficeProgramme[];
}

/** Un KPI en las dos oficinas, siempre Valencia y después Miami. */
export function kpiByOffice(entries: readonly WeeklyPerformanceEntry[], key: KpiKey): OfficeKpi[] {
  return REPORT_OFFICES.map((office) => {
    const rows = entries
      .filter((entry) => entry.office === office)
      .sort((a, b) => compareProgrammes(a.programme_id, b.programme_id));
    return {
      office,
      officeLabel: OFFICE_LABELS[office],
      currency: CURRENCY_BY_OFFICE[office],
      hasActivity: rows.length > 0,
      total: rows.length > 0 ? officeTotal(rows, key) : 0,
      programmes: rows.map((row) => ({
        programmeId: row.programme_id,
        label: programmeLabel(row.programme_id),
        value: entryValue(row, key),
      })),
    };
  });
}

/** Escala común de las barras de un KPI de conteo: el mayor subtotal de las dos oficinas. */
export function commonScale(offices: readonly OfficeKpi[]): number {
  return Math.max(0, ...offices.map((office) => office.total));
}

/** Largo de la barra, 0–100. */
export function barPercent(value: number, scale: number): number {
  return scale <= 0 ? 0 : Math.min(100, (value / scale) * 100);
}

const COUNT = new Intl.NumberFormat('es-ES', { maximumFractionDigits: 0 });

export function formatCount(value: number): string {
  return COUNT.format(value);
}

/** `56.5`, `EUR` → «56,50 €». */
export function formatMoney(amount: number, currency: Currency): string {
  return new Intl.NumberFormat('es-ES', { style: 'currency', currency }).format(amount);
}

// ---------------------------------------------------------------------------
// Semanas (lunes a domingo, UTC)
// ---------------------------------------------------------------------------

const WEEKDAYS = ['domingo', 'lunes', 'martes', 'miércoles', 'jueves', 'viernes', 'sábado'] as const;
const MONTHS = [
  'enero',
  'febrero',
  'marzo',
  'abril',
  'mayo',
  'junio',
  'julio',
  'agosto',
  'septiembre',
  'octubre',
  'noviembre',
  'diciembre',
] as const;
const DAY_MS = 24 * 60 * 60 * 1000;

function parseIsoDate(iso: string): Date | null {
  const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(iso);
  if (match === null) return null;
  const date = new Date(Date.UTC(Number(match[1]), Number(match[2]) - 1, Number(match[3])));
  return Number.isNaN(date.getTime()) ? null : date;
}

function toIso(date: Date): string {
  return date.toISOString().slice(0, 10);
}

/** `2026-11-02`, `-1` → `2026-10-26`. Una fecha ilegible se devuelve tal cual. */
export function shiftWeek(weekStart: string, weeks: number): string {
  const date = parseIsoDate(weekStart);
  return date === null ? weekStart : toIso(new Date(date.getTime() + weeks * 7 * DAY_MS));
}

/** El domingo de la semana que empieza el `weekStart`. */
export function weekEnd(weekStart: string): string {
  const date = parseIsoDate(weekStart);
  return date === null ? weekStart : toIso(new Date(date.getTime() + 6 * DAY_MS));
}

function part(date: Date) {
  return { weekday: WEEKDAYS[date.getUTCDay()], day: date.getUTCDate(), month: MONTHS[date.getUTCMonth()], year: date.getUTCFullYear() };
}

/** «lunes 2 al domingo 8 de noviembre de 2026» (los meses y años que cambien, también). */
function rangeText(startIso: string, endIso: string): string | null {
  const start = parseIsoDate(startIso);
  const end = parseIsoDate(endIso);
  if (start === null || end === null) return null;
  const a = part(start);
  const b = part(end);
  const sameYear = a.year === b.year;
  const sameMonth = sameYear && a.month === b.month;
  const first = sameMonth ? `${a.weekday} ${a.day}` : `${a.weekday} ${a.day} de ${a.month}${sameYear ? '' : ` de ${a.year}`}`;
  return `${first} al ${b.weekday} ${b.day} de ${b.month} de ${b.year}`;
}

/** «Semana del lunes 2 al domingo 8 de noviembre de 2026». */
export function weekPeriodLabel(weekStart: string): string {
  const text = rangeText(weekStart, weekEnd(weekStart));
  return text === null ? `Semana del ${weekStart}` : `Semana del ${text}`;
}

// ---------------------------------------------------------------------------
// Frescura de los datos (última corrida del pipeline)
// ---------------------------------------------------------------------------

export interface Freshness {
  tone: 'ok' | 'info' | 'problem' | 'none';
  headline: string;
  detail: string | null;
  /** Una corrida completada hace más de `STALE_AFTER_DAYS` días. */
  stale: boolean;
}

/** Instante en hora local, legible. `timeZone` solo para los tests. */
export function formatInstant(iso: string, timeZone?: string): string {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return iso;
  return new Intl.DateTimeFormat('es-ES', { dateStyle: 'long', timeStyle: 'short', timeZone }).format(date);
}

export function describeFreshness(run: PipelineRun | null, now: Date, timeZone?: string): Freshness {
  if (run === null) {
    return { tone: 'none', headline: 'El reporte todavía no se ha calculado.', detail: null, stale: false };
  }
  if (run.status === 'running') {
    return { tone: 'info', headline: 'Actualizando los datos…', detail: null, stale: false };
  }
  if (run.status === 'failed') {
    return {
      tone: 'problem',
      headline: 'La última actualización falló; las cifras pueden ser de una corrida anterior.',
      detail: null,
      stale: false,
    };
  }
  const finished = run.finished_at ?? run.started_at;
  const finishedAt = new Date(finished);
  const stale = !Number.isNaN(finishedAt.getTime()) && now.getTime() - finishedAt.getTime() > STALE_AFTER_DAYS * DAY_MS;
  const covered = rangeText(run.week_from, weekEnd(run.week_to));
  return {
    tone: 'ok',
    headline: `Datos actualizados el ${formatInstant(finished, timeZone)}.`,
    detail: covered === null ? null : `Semanas calculadas: del ${covered}.`,
    stale,
  };
}

// ---------------------------------------------------------------------------
// Textos de error: sin códigos, sin nombres técnicos
// ---------------------------------------------------------------------------

export function reportingErrorCopy(error: ReportingUiError): { title: string; body: string } {
  switch (error.kind) {
    case 'network':
      return {
        title: 'No se pudo conectar con el servidor',
        body: 'Comprueba tu conexión e inténtalo de nuevo. Si el problema continúa, avisa al equipo técnico.',
      };
    case 'timeout':
      return { title: 'La operación tardó demasiado', body: 'El servidor no respondió a tiempo. Inténtalo de nuevo.' };
    case 'storage_unavailable':
      return {
        title: 'Los datos no están disponibles ahora mismo',
        body: 'El almacén de datos no responde. Inténtalo de nuevo en unos minutos.',
      };
    case 'server_error':
      return { title: 'Error del servidor', body: 'No se pudo cargar el reporte. Inténtalo de nuevo en unos minutos.' };
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

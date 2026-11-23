// lib/telemetry-report-format.ts: presentación de /telemetry. La API no redondea:
// aquí se formatean las tasas y se agrupa el volumen por día.

import {
  ERROR_CLASS_LABELS,
  TASK_PHASE_COPY,
  dailyVolumes,
  formatMs,
  formatPercent,
  formatPeriodDate,
  telemetryReportErrorCopy,
  volumeServices,
} from '@/lib/telemetry-report-format';
import type { TelemetryReportUiError } from '@/types/telemetry-report';

// `Intl` separa el porcentaje con un espacio de no separación.
const normalized = (text: string) => text.replace(/\s/g, ' ');

describe('formatPercent', () => {
  it('deja un decimal como mucho', () => {
    expect(normalized(formatPercent(0.057692307692307696))).toBe('5,8 %');
  });

  it('muestra el 100 % y el 0 % sin decimales', () => {
    expect(normalized(formatPercent(1))).toBe('100 %');
    expect(normalized(formatPercent(0))).toBe('0 %');
  });
});

describe('formatMs', () => {
  it('redondea para mostrar, sin tocar el dato', () => {
    expect(formatMs(478.75)).toBe('479 ms');
  });
});

describe('formatPeriodDate', () => {
  it('muestra la fecha en la zona pedida', () => {
    expect(formatPeriodDate('2026-11-05T23:39:03.085Z', 'Europe/Madrid')).toContain('6 nov 2026');
  });

  it('una fecha ilegible se muestra tal cual', () => {
    expect(formatPeriodDate('no-es-fecha')).toBe('no-es-fecha');
  });
});

describe('dailyVolumes', () => {
  const rows = [
    { day: '2026-11-04', service: 'backoffice', events: 0 },
    { day: '2026-11-04', service: 'api', events: 1 },
    { day: '2026-11-05', service: 'backoffice', events: 55 },
    { day: '2026-11-05', service: 'api', events: 0 },
  ];

  it('agrupa por día y suma los service', () => {
    expect(dailyVolumes(rows).map((item) => [item.day, item.total])).toEqual([
      ['2026-11-04', 1],
      ['2026-11-05', 55],
    ]);
  });

  it('la barra es proporcional al día con más eventos', () => {
    const [low, high] = dailyVolumes(rows);
    expect(high?.barPercent).toBe(100);
    expect(low?.barPercent).toBeCloseTo(100 / 55);
  });

  it('un periodo a 0 mantiene los días y no divide entre cero', () => {
    const volumes = dailyVolumes([{ day: '2026-11-01', service: 'api', events: 0 }]);
    expect(volumes).toEqual([{ day: '2026-11-01', services: [{ service: 'api', events: 0 }], total: 0, barPercent: 0 }]);
  });

  it('las columnas son los service, en orden de aparición', () => {
    expect(volumeServices(rows)).toEqual(['backoffice', 'api']);
  });
});

describe('ERROR_CLASS_LABELS', () => {
  it('etiqueta las dos clases', () => {
    expect(ERROR_CLASS_LABELS).toEqual({ system: 'Sistema', rejected: 'Rechazado' });
  });
});

// DEV-55 (parada 4): textos de las fases de la tarea y de cada error, movidos aquí
// desde la vista para poder probarlos.
describe('textos de la cola de tareas', () => {
  const KINDS: TelemetryReportUiError['kind'][] = [
    'queue_unavailable',
    'task_failed',
    'task_expired',
    'polling_timeout',
    'request_invalid',
    'server_error',
    'network',
    'timeout',
    'unexpected_response',
    'config',
    'session_expired',
  ];

  test('las dos fases se llaman «En cola» y «Calculando»', () => {
    expect(TASK_PHASE_COPY.queued.title).toBe('En cola');
    expect(TASK_PHASE_COPY.computing.title).toBe('Calculando');
  });

  test('cada error tiene un título y un texto propios', () => {
    const titles = new Set(KINDS.map((kind) => telemetryReportErrorCopy({ kind } as TelemetryReportUiError).title));
    expect(titles.size).toBe(KINDS.length);
  });

  test('ningún texto muestra códigos HTTP, nombres de la API ni detalles técnicos', () => {
    for (const kind of KINDS) {
      const { title, body } = telemetryReportErrorCopy({ kind } as TelemetryReportUiError);
      expect(`${title} ${body}`).not.toMatch(/\b[45]\d\d\b|task_|queue_|redis|celery|NEXT_PUBLIC|services\/api|\(.*\)/i);
    }
  });

  test('los casos de la cola dicen qué hacer', () => {
    expect(telemetryReportErrorCopy({ kind: 'queue_unavailable' }).body).toMatch(/Inténtalo de nuevo/);
    expect(telemetryReportErrorCopy({ kind: 'task_expired' }).body).toMatch(/Pídelo de nuevo/);
    expect(telemetryReportErrorCopy({ kind: 'polling_timeout' }).body).toMatch(/10 minutos/);
  });
});

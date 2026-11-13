// lib/reporting-format.ts: presentación de /reporting. Rango de la semana, subtotales por oficina
// (EUR y USD nunca se suman), formato de moneda, el centinela de programa, las barras y la frescura.

import {
  CURRENCY_NOTE,
  KPIS,
  MixedCurrencyError,
  STALE_AFTER_DAYS,
  UNASSIGNED_LABEL,
  allUnassigned,
  barPercent,
  commonScale,
  compareProgrammes,
  describeFreshness,
  formatCount,
  formatMoney,
  kpiByOffice,
  officeTotal,
  programmeLabel,
  reportingErrorCopy,
  shiftWeek,
  weekEnd,
  weekPeriodLabel,
} from '@/lib/reporting-format';
import type { PipelineRun, ReportingUiError, WeeklyPerformanceEntry } from '@/types/reporting';

// `Intl` separa la cifra de la moneda con un espacio de no separación.
const normalized = (text: string) => text.replace(/\s/g, ' ');

function entry(overrides: Partial<WeeklyPerformanceEntry> = {}): WeeklyPerformanceEntry {
  return {
    office: 'valencia',
    programme_id: '_unassigned',
    total_material_cost: 0,
    kits_delivered_count: 0,
    shortage_events_count: 0,
    cost_variance_events_count: 0,
    currency: 'EUR',
    ...overrides,
  };
}

const miami = (overrides: Partial<WeeklyPerformanceEntry> = {}) => entry({ office: 'miami', currency: 'USD', ...overrides });

describe('KPIS', () => {
  it('lleva los cuatro nombres del BRIEFING, en orden', () => {
    expect(KPIS.map((kpi) => kpi.title)).toEqual([
      'Costo de material por oficina/programa',
      'Kits entregados',
      'Frecuencia de escasez',
      'Frecuencia de variación de costo',
    ]);
    expect(KPIS.map((kpi) => kpi.key)).toEqual([
      'total_material_cost',
      'kits_delivered_count',
      'shortage_events_count',
      'cost_variance_events_count',
    ]);
  });

  it('cada KPI trae su frase «qué mide» y solo el costo es dinero', () => {
    for (const kpi of KPIS) expect(kpi.question.endsWith('.')).toBe(true);
    expect(KPIS.filter((kpi) => kpi.kind === 'money').map((kpi) => kpi.key)).toEqual(['total_material_cost']);
  });
});

describe('weekPeriodLabel, weekEnd y shiftWeek', () => {
  it('la semana del lunes al domingo, en el mismo mes', () => {
    expect(weekPeriodLabel('2026-11-02')).toBe('Semana del lunes 2 al domingo 8 de noviembre de 2026');
  });

  it('una semana que cambia de mes, o de año', () => {
    expect(weekPeriodLabel('2026-10-26')).toBe('Semana del lunes 26 de octubre al domingo 1 de noviembre de 2026');
    expect(weekPeriodLabel('2026-12-28')).toBe('Semana del lunes 28 de diciembre de 2026 al domingo 3 de enero de 2027');
  });

  it('el domingo es seis días después y las semanas se desplazan de siete en siete', () => {
    expect(weekEnd('2026-11-02')).toBe('2026-11-08');
    expect(shiftWeek('2026-11-02', -1)).toBe('2026-10-26');
    expect(shiftWeek('2026-10-26', 2)).toBe('2026-11-09');
  });

  it('una fecha ilegible se devuelve tal cual', () => {
    expect(shiftWeek('noviembre', 1)).toBe('noviembre');
    expect(weekPeriodLabel('noviembre')).toBe('Semana del noviembre');
  });
});

describe('formatMoney y formatCount', () => {
  it('cada oficina con su moneda', () => {
    expect(normalized(formatMoney(56.5, 'EUR'))).toBe('56,50 €');
    expect(normalized(formatMoney(120, 'USD'))).toContain('120,00');
    expect(normalized(formatMoney(120, 'USD'))).toMatch(/\$/);
  });

  it('los conteos, sin decimales', () => {
    expect(formatCount(1234)).toMatch(/^1\.?234$/);
    expect(formatCount(0)).toBe('0');
  });
});

describe('programmeLabel, compareProgrammes y allUnassigned', () => {
  it('nunca muestra el centinela', () => {
    expect(programmeLabel('_unassigned')).toBe(UNASSIGNED_LABEL);
    expect(UNASSIGNED_LABEL).toBe('Sin programa asignado');
    expect(programmeLabel('programa-ficticio')).toBe('programa-ficticio');
  });

  it('los programas reales primero, y «sin asignar» al final', () => {
    expect(['_unassigned', 'zeta', 'alfa'].sort(compareProgrammes)).toEqual(['alfa', 'zeta', '_unassigned']);
  });

  it('allUnassigned: todo sin clasificar y al menos una fila', () => {
    expect(allUnassigned([])).toBe(false);
    expect(allUnassigned([entry(), miami()])).toBe(true);
    expect(allUnassigned([entry(), miami({ programme_id: 'programa-ficticio' })])).toBe(false);
  });
});

describe('officeTotal', () => {
  it('suma el costo en céntimos enteros, sin el error de los flotantes', () => {
    const rows = [entry({ total_material_cost: 0.1 }), entry({ programme_id: 'a', total_material_cost: 0.2 })];
    expect(officeTotal(rows, 'total_material_cost')).toBe(0.3);
    expect(0.1 + 0.2).not.toBe(0.3);
  });

  it('suma los conteos de los programas de una oficina', () => {
    const rows = [entry({ kits_delivered_count: 2 }), entry({ programme_id: 'a', kits_delivered_count: 3 })];
    expect(officeTotal(rows, 'kits_delivered_count')).toBe(5);
  });

  it('una sola oficina vacía suma cero', () => {
    expect(officeTotal([], 'kits_delivered_count')).toBe(0);
  });

  it('lanza si recibe dos monedas: nunca hay un total entre Valencia y Miami', () => {
    const mixed = [entry({ total_material_cost: 10 }), miami({ total_material_cost: 10 })];
    expect(() => officeTotal(mixed, 'total_material_cost')).toThrow(MixedCurrencyError);
    expect(() => officeTotal(mixed, 'kits_delivered_count')).toThrow(MixedCurrencyError);
  });
});

describe('kpiByOffice, commonScale y barPercent', () => {
  const entries = [
    entry({ programme_id: 'a', total_material_cost: 100, kits_delivered_count: 3 }),
    entry({ programme_id: '_unassigned', total_material_cost: 50.5, kits_delivered_count: 1 }),
    miami({ total_material_cost: 40.2, kits_delivered_count: 8 }),
  ];

  it('siempre Valencia y después Miami, cada una con su moneda', () => {
    const offices = kpiByOffice(entries, 'total_material_cost');
    expect(offices.map((office) => [office.officeLabel, office.currency])).toEqual([
      ['Valencia', 'EUR'],
      ['Miami', 'USD'],
    ]);
    expect(offices.map((office) => office.total)).toEqual([150.5, 40.2]);
  });

  it('los programas, con el centinela al final y con su etiqueta', () => {
    const [valencia] = kpiByOffice(entries, 'kits_delivered_count');
    expect(valencia.programmes.map((programme) => [programme.label, programme.value])).toEqual([
      ['a', 3],
      [UNASSIGNED_LABEL, 1],
    ]);
  });

  it('una oficina sin filas no inventa un cero: no tiene actividad', () => {
    const [valencia, miamiOffice] = kpiByOffice([entry({ kits_delivered_count: 2 })], 'kits_delivered_count');
    expect(valencia.hasActivity).toBe(true);
    expect(miamiOffice.hasActivity).toBe(false);
    expect(miamiOffice.programmes).toEqual([]);
  });

  it('la escala de las barras es común a las dos oficinas', () => {
    const offices = kpiByOffice(entries, 'kits_delivered_count');
    expect(commonScale(offices)).toBe(8);
    expect(offices.map((office) => barPercent(office.total, commonScale(offices)))).toEqual([50, 100]);
  });

  it('sin actividad la barra mide cero, y nunca pasa de 100', () => {
    expect(barPercent(0, 0)).toBe(0);
    expect(barPercent(5, 0)).toBe(0);
    expect(barPercent(12, 8)).toBe(100);
  });
});

describe('describeFreshness', () => {
  const NOW = new Date('2026-11-12T12:00:00Z');
  const completed: PipelineRun = {
    status: 'completed',
    started_at: '2026-11-09T05:00:00Z',
    finished_at: '2026-11-09T05:00:07Z',
    week_from: '2026-10-26',
    week_to: '2026-11-02',
  };

  it('una corrida completada: cuándo y qué semanas cubrió', () => {
    const freshness = describeFreshness(completed, NOW, 'Europe/Madrid');
    expect(freshness.tone).toBe('ok');
    expect(freshness.headline).toContain('9 de noviembre de 2026');
    expect(freshness.detail).toBe('Semanas calculadas: del lunes 26 de octubre al domingo 8 de noviembre de 2026.');
    expect(freshness.stale).toBe(false);
  });

  it(`pasados ${STALE_AFTER_DAYS} días, desactualizado; justo antes, no`, () => {
    const day = 24 * 60 * 60 * 1000;
    const finished = new Date(completed.finished_at as string).getTime();
    expect(describeFreshness(completed, new Date(finished + 8 * day), 'UTC').stale).toBe(false);
    expect(describeFreshness(completed, new Date(finished + 8 * day + 1000), 'UTC').stale).toBe(true);
  });

  it('en marcha, fallida y sin corridas', () => {
    expect(describeFreshness({ ...completed, status: 'running', finished_at: null }, NOW).headline).toBe('Actualizando los datos…');
    const failed = describeFreshness({ ...completed, status: 'failed' }, NOW);
    expect(failed.tone).toBe('problem');
    expect(failed.headline).toBe('La última actualización falló; las cifras pueden ser de una corrida anterior.');
    expect(describeFreshness(null, NOW).headline).toBe('El reporte todavía no se ha calculado.');
  });

  it('una fecha ilegible no marca desactualizado', () => {
    expect(describeFreshness({ ...completed, finished_at: 'ayer' }, NOW).stale).toBe(false);
  });
});

describe('textos', () => {
  const KINDS: ReportingUiError['kind'][] = [
    'request_invalid',
    'server_error',
    'storage_unavailable',
    'network',
    'timeout',
    'unexpected_response',
    'config',
    'session_expired',
  ];

  it('los errores no llevan códigos, nombres técnicos ni números', () => {
    for (const kind of KINDS) {
      const { title, body } = reportingErrorCopy({ kind } as ReportingUiError);
      expect(`${title} ${body}`).not.toMatch(/\d|_|NEXT_PUBLIC|error_class|storage_unavailable|HTTP|API/i);
    }
  });

  it('el 503 de almacenamiento tiene su propio texto', () => {
    expect(reportingErrorCopy({ kind: 'storage_unavailable' }).title).toBe('Los datos no están disponibles ahora mismo');
  });

  it('la nota de monedas nombra las dos y dice que no se suman', () => {
    expect(CURRENCY_NOTE).toBe('Valencia se expresa en euros y Miami en dólares; las cifras no se suman ni se convierten.');
  });
});

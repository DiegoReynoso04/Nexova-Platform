'use client';

// /telemetry: las métricas técnicas de `GET /telemetry/report`, con el periodo
// visible. Tablas, y una barra de CSS por día en el volumen: sin librería de
// gráficos. Los valores de la API se muestran tal cual, en inglés.

import type { ReactNode } from 'react';

import { Alert } from '@/components/ui/alert';
import { Button } from '@/components/ui/button';
import { LoadingSpinner } from '@/components/ui/loading-spinner';
import { TableScroll } from '@/components/ui/table-scroll';
import { useTelemetryReport } from '@/hooks/use-telemetry-report';
import {
  ERROR_CLASS_LABELS,
  dailyVolumes,
  formatMs,
  formatPercent,
  formatPeriodDate,
  volumeServices,
} from '@/lib/telemetry-report-format';
import type { TelemetryReport, TelemetryReportUiError } from '@/types/telemetry-report';

const TABLE_CLASSES = 'w-full border-collapse text-left text-sm';
const HEAD_CLASSES = 'border-b border-border bg-canvas text-xs uppercase tracking-wide text-ink-muted';
const HEADER_CELL = 'px-3 py-2 font-semibold';
const NUMBER_HEADER = `${HEADER_CELL} text-right`;
const ROW_CLASSES = 'border-b border-border last:border-b-0';
const CELL = 'px-3 py-2';
const NUMBER_CELL = 'px-3 py-2 text-right tabular-nums';
const CODE_CELL = 'px-3 py-2 font-mono text-xs';

function errorCopy(error: TelemetryReportUiError): { title: string; body: string } {
  switch (error.kind) {
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

function ReportError({ error, onRetry }: { error: TelemetryReportUiError; onRetry: () => void }) {
  const { title, body } = errorCopy(error);
  return (
    <div className="flex flex-col gap-2">
      <Alert variant="error" title={title}>
        {body}
      </Alert>
      <div>
        <Button variant="secondary" onClick={onRetry}>
          Reintentar
        </Button>
      </div>
    </div>
  );
}

function Metric({ title, question, note, children }: { title: string; question: string; note?: string; children: ReactNode }) {
  return (
    <section className="flex flex-col gap-2">
      <div>
        <h2 className="text-base font-semibold text-ink">{title}</h2>
        <p className="text-sm text-ink-muted">{question}</p>
      </div>
      {children}
      {note !== undefined && <p className="text-xs text-ink-muted">{note}</p>}
    </section>
  );
}

function NoData() {
  return <p className="rounded-lg border border-dashed border-border bg-surface p-4 text-sm text-ink-muted">Sin datos en este periodo.</p>;
}

function Period({ period }: { period: TelemetryReport['period'] }) {
  return (
    <p className="rounded-lg border border-border bg-surface px-4 py-3 text-sm text-ink">
      <span className="font-semibold">Periodo analizado:</span> del <time dateTime={period.from}>{formatPeriodDate(period.from)}</time> al{' '}
      <time dateTime={period.to}>{formatPeriodDate(period.to)}</time>, en tu hora local. Cada día de las tablas es un día UTC.
    </p>
  );
}

function EventsPerDay({ report }: { report: TelemetryReport }) {
  const rows = report.metrics.events_per_day;
  const services = volumeServices(rows);
  return (
    <TableScroll framed>
      <table className={`${TABLE_CLASSES} min-w-[32rem]`}>
        <caption className="sr-only">Eventos guardados por día y por origen</caption>
        <thead className={HEAD_CLASSES}>
          <tr>
            <th scope="col" className={HEADER_CELL}>Día</th>
            {services.map((service) => (
              <th key={service} scope="col" className={NUMBER_HEADER}>{service}</th>
            ))}
            <th scope="col" className={NUMBER_HEADER}>Total</th>
            <th scope="col" className={`${HEADER_CELL} w-1/3`}><span className="sr-only">Barra del total</span></th>
          </tr>
        </thead>
        <tbody>
          {dailyVolumes(rows).map((item) => (
            <tr key={item.day} className={ROW_CLASSES}>
              <th scope="row" className={`${CELL} whitespace-nowrap font-medium text-ink`}>{item.day}</th>
              {item.services.map(({ service, events }) => (
                <td key={service} className={NUMBER_CELL}>{events}</td>
              ))}
              <td className={`${NUMBER_CELL} font-semibold`}>{item.total}</td>
              <td className={CELL}>
                {/* Decorativa: el número ya está en la celda anterior. */}
                <div aria-hidden="true" className="h-2 rounded-r bg-brand" style={{ width: `${item.barPercent}%` }} />
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </TableScroll>
  );
}

function ErrorRates({ report }: { report: TelemetryReport }) {
  const rows = report.metrics.error_rate_by_type;
  if (rows.length === 0) return <NoData />;
  return (
    <TableScroll framed>
      <table className={`${TABLE_CLASSES} min-w-[40rem]`}>
        <caption className="sr-only">Errores por día y por tipo</caption>
        <thead className={HEAD_CLASSES}>
          <tr>
            <th scope="col" className={HEADER_CELL}>Día</th>
            <th scope="col" className={HEADER_CELL}>Tipo</th>
            <th scope="col" className={HEADER_CELL}>Clase</th>
            <th scope="col" className={NUMBER_HEADER}>Errores</th>
            <th scope="col" className={NUMBER_HEADER}>Eventos del día</th>
            <th scope="col" className={NUMBER_HEADER}>Tasa</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={`${row.day}-${row.error_type}`} className={ROW_CLASSES}>
              <td className={`${CELL} whitespace-nowrap`}>{row.day}</td>
              <td className={CODE_CELL}>{row.error_type}</td>
              <td className={CELL}>{ERROR_CLASS_LABELS[row.error_class]}</td>
              <td className={NUMBER_CELL}>{row.errors}</td>
              <td className={NUMBER_CELL}>{row.total_events}</td>
              <td className={NUMBER_CELL}>{formatPercent(row.error_rate)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </TableScroll>
  );
}

function PageLoads({ report }: { report: TelemetryReport }) {
  const rows = report.metrics.page_load_latency_by_route;
  if (rows.length === 0) return <NoData />;
  return (
    <TableScroll framed>
      <table className={`${TABLE_CLASSES} min-w-[36rem]`}>
        <caption className="sr-only">Espera de las páginas de datos por día, ruta y resultado</caption>
        <thead className={HEAD_CLASSES}>
          <tr>
            <th scope="col" className={HEADER_CELL}>Día</th>
            <th scope="col" className={HEADER_CELL}>Ruta</th>
            <th scope="col" className={HEADER_CELL}>Resultado</th>
            <th scope="col" className={NUMBER_HEADER}>Cargas</th>
            <th scope="col" className={NUMBER_HEADER}>Media</th>
            <th scope="col" className={NUMBER_HEADER}>Máximo</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={`${row.day}-${row.route_template}-${row.outcome}`} className={ROW_CLASSES}>
              <td className={`${CELL} whitespace-nowrap`}>{row.day}</td>
              <td className={CODE_CELL}>{row.route_template}</td>
              <td className={CODE_CELL}>{row.outcome}</td>
              <td className={NUMBER_CELL}>{row.loads}</td>
              <td className={NUMBER_CELL}>{formatMs(row.avg_ms)}</td>
              <td className={NUMBER_CELL}>{formatMs(row.max_ms)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </TableScroll>
  );
}

function DominantTypes({ report }: { report: TelemetryReport }) {
  const rows = report.metrics.dominant_event_types;
  if (rows.length === 0) return <NoData />;
  return (
    <TableScroll framed>
      <table className={`${TABLE_CLASSES} min-w-[28rem]`}>
        <caption className="sr-only">Tipos de evento de mayor a menor</caption>
        <thead className={HEAD_CLASSES}>
          <tr>
            <th scope="col" className={HEADER_CELL}>Tipo</th>
            <th scope="col" className={HEADER_CELL}>Origen</th>
            <th scope="col" className={NUMBER_HEADER}>Eventos</th>
            <th scope="col" className={NUMBER_HEADER}>Peso</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={`${row.event_type}-${row.service}`} className={ROW_CLASSES}>
              <td className={CODE_CELL}>{row.event_type}</td>
              <td className={CODE_CELL}>{row.service}</td>
              <td className={NUMBER_CELL}>{row.events}</td>
              <td className={NUMBER_CELL}>{formatPercent(row.share)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </TableScroll>
  );
}

function AuthFailures({ report }: { report: TelemetryReport }) {
  const rows = report.metrics.auth_failure_rate;
  if (rows.length === 0) return <NoData />;
  return (
    <TableScroll framed>
      <table className={`${TABLE_CLASSES} min-w-[28rem]`}>
        <caption className="sr-only">Logins fallidos por día</caption>
        <thead className={HEAD_CLASSES}>
          <tr>
            <th scope="col" className={HEADER_CELL}>Día</th>
            <th scope="col" className={NUMBER_HEADER}>Fallidos</th>
            <th scope="col" className={NUMBER_HEADER}>Correctos</th>
            <th scope="col" className={NUMBER_HEADER}>Intentos</th>
            <th scope="col" className={NUMBER_HEADER}>Tasa de fallo</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={row.day} className={ROW_CLASSES}>
              <td className={`${CELL} whitespace-nowrap`}>{row.day}</td>
              <td className={NUMBER_CELL}>{row.failed}</td>
              <td className={NUMBER_CELL}>{row.succeeded}</td>
              <td className={NUMBER_CELL}>{row.attempts}</td>
              <td className={NUMBER_CELL}>{formatPercent(row.failure_rate)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </TableScroll>
  );
}

export function TelemetryReportView() {
  const { report, load, view, reload } = useTelemetryReport();

  return (
    <div className="flex flex-col gap-6">
      {view === 'loading' && (
        <div className="flex items-center gap-3 rounded-lg border border-dashed border-border bg-surface p-6">
          <LoadingSpinner />
          <span className="text-sm text-ink-muted">Calculando el reporte…</span>
        </div>
      )}

      {load.status === 'error' && <ReportError error={load.error} onRetry={reload} />}

      {report !== null && (
        <>
          <Period period={report.period} />
          <Metric title="Eventos por día" question="¿Llega telemetría cada día, y de quién? Un día a 0 puede ser un colector caído.">
            <EventsPerDay report={report} />
          </Metric>
          <Metric
            title="Errores por tipo"
            question="¿Qué falla, cuánto pesa, y es el sistema o el usuario?"
            note="La tasa es la proporción de eventos técnicos del día, no de peticiones: las correctas no se registran. Con pocos eventos en un día, un solo error pesa mucho."
          >
            <ErrorRates report={report} />
          </Metric>
          <Metric
            title="Espera por página"
            question="¿En qué sección esperan más los operadores a ver los datos?"
            note="Es la espera en el navegador, no el tiempo de la API."
          >
            <PageLoads report={report} />
          </Metric>
          <Metric title="Tipos de evento dominantes" question="¿Qué tipos ocupan más la tabla de telemetría?">
            <DominantTypes report={report} />
          </Metric>
          <Metric
            title="Logins fallidos"
            question="¿Cuántos logins fallan al día desde el backoffice?"
            note="Solo cuenta lo que pasa por el navegador."
          >
            <AuthFailures report={report} />
          </Metric>
        </>
      )}
    </div>
  );
}

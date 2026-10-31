'use client';

// Vista de /incidents: conecta el hook con componentes presentacionales.
// No hace HTTP ni lee el archivo: todo pasa por useIncidentAnalysis y, para la
// ayuda inmediata de extensión/tamaño, por la misma prevalidación del servicio.

import dynamic from 'next/dynamic';
import { useEffect, useRef } from 'react';

import { Alert } from '@/components/ui/alert';
import { LoadingSpinner } from '@/components/ui/loading-spinner';
import { useIncidentAnalysis } from '@/hooks/use-incident-analysis';
import { precheckFile } from '@/services/incidents.service';

import { AnalysisError } from './analysis-error';
import { AnalysisMeta } from './analysis-meta';
import { UploadForm } from './upload-form';

// Carga diferida (docs/caching-analysis.md, D6): las métricas solo existen tras
// analizar un CSV, así que van en un chunk aparte que se pide al elegir el
// archivo (antes de pulsar «Analizar»). Si aún no ha llegado al mostrar el
// resultado, `ResultsPlaceholder` reserva su alto para no desplazar nada (CLS).
const loadIncidentResults = () => import('./incident-results');
const IncidentResults = dynamic(() => loadIncidentResults().then((module) => module.IncidentResults), {
  loading: ResultsPlaceholder,
});

// Alto medido de las métricas en el build de producción (2026-10-31): 1850 px a
// 375 px (una columna) y 1249 px desde `lg` (dos columnas). Varía un poco con el
// número de reglas, categorías y estados del CSV.
function ResultsPlaceholder() {
  return (
    <div aria-busy="true" className="min-h-[1850px] lg:min-h-[1249px]">
      <span className="sr-only">Cargando resultados…</span>
    </div>
  );
}

export function IncidentAnalysisView() {
  const { file, result, analysis, exporting, analysisError, exportError, selectFile, analyze, exportResults } =
    useIncidentAnalysis();

  // Derivado en cada render (no se guarda): misma regla que aplica el servicio.
  const precheckError = file === null ? null : precheckFile(file);
  const isAnalyzing = analysis.status === 'loading';
  const isExporting = exporting.status === 'loading';

  // Al aparecer un resultado nuevo, el foco va a su encabezado.
  const resultsHeadingRef = useRef<HTMLHeadingElement>(null);
  const analysisId = result?.analysis_id;
  useEffect(() => {
    if (analysisId !== undefined) resultsHeadingRef.current?.focus();
  }, [analysisId]);

  // Elegir un archivo anuncia un análisis: se adelanta el chunk de las métricas.
  const hasFile = file !== null;
  useEffect(() => {
    if (hasFile) void loadIncidentResults();
  }, [hasFile]);

  let liveMessage = '';
  if (isAnalyzing) liveMessage = 'Analizando el archivo…';
  else if (analysis.status === 'success') liveMessage = 'Análisis completado.';
  if (isExporting) liveMessage = 'Preparando la descarga…';
  else if (exporting.status === 'success' && result !== null) liveMessage = `Descarga de ${result.export.filename} iniciada.`;

  return (
    <>
      {/* Anuncios de estado para lectores de pantalla; los errores se anuncian con role="alert". */}
      <p role="status" className="sr-only">
        {liveMessage}
      </p>

      <section aria-labelledby="upload-heading" className="rounded-lg border border-border bg-surface p-4 sm:p-6">
        <h2 id="upload-heading" className="text-base font-semibold text-ink">
          Archivo
        </h2>
        <div className="mt-4 flex flex-col gap-4">
          <UploadForm
            file={file}
            precheckError={precheckError}
            isAnalyzing={isAnalyzing}
            onFileChange={selectFile}
            onAnalyze={analyze}
          />
          {analysisError !== null && (
            <div className="flex flex-col gap-2">
              <AnalysisError error={analysisError} />
              {result !== null && (
                <p className="text-xs text-ink-muted">Se siguen mostrando los resultados del análisis anterior.</p>
              )}
            </div>
          )}
        </div>
      </section>

      {result === null ? (
        <section
          aria-labelledby="results-empty-heading"
          className="rounded-lg border border-dashed border-border bg-surface p-6 text-center"
        >
          {isAnalyzing ? (
            <div className="flex flex-col items-center gap-3">
              <LoadingSpinner />
              <h2 id="results-empty-heading" className="text-sm font-medium text-ink">
                Analizando el archivo…
              </h2>
            </div>
          ) : (
            <>
              <h2 id="results-empty-heading" className="text-sm font-medium text-ink">
                Todavía no hay resultados
              </h2>
              <p className="mt-1 text-sm text-ink-muted">
                Selecciona el CSV de incidentes y pulsa «Analizar» para ver las métricas.
              </p>
            </>
          )}
        </section>
      ) : (
        <section aria-labelledby="results-heading" className="flex flex-col gap-4">
          <div className="flex flex-col gap-2">
            <h2
              id="results-heading"
              ref={resultsHeadingRef}
              tabIndex={-1}
              className="text-base font-semibold text-ink outline-none focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand"
            >
              Resultados
            </h2>
            {isAnalyzing && (
              <Alert variant="info" title="Analizando un archivo nuevo">
                <p>Mientras tanto se muestran los resultados del análisis anterior.</p>
              </Alert>
            )}
            <AnalysisMeta result={result} isExporting={isExporting} exportError={exportError} onExport={exportResults} />
          </div>

          <IncidentResults result={result} />
        </section>
      )}
    </>
  );
}

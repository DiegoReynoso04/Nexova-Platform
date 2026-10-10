'use client';

// Límite de error global (Next 16, `app/global-error.tsx`): solo se activa si
// falla el propio layout raíz, y entonces lo sustituye. Por eso renderiza su
// propio <html>/<body>, importa los estilos globales y no depende del layout,
// de los avisos, del SessionProvider ni del AuthGuard (no lo envuelven).
// Firma de props de Next 16.3: `{ error: Error & { digest?: string }; retry: () => void }`.
//
// Privacidad: el error no se muestra ni se registra (ni mensaje, ni `digest`,
// ni traza). El enlace a inicio es un <a> normal: recarga la app entera, que
// es lo que hace falta si el layout raíz ha fallado.

import { Button } from '@/components/ui/button';
import { HOME_PATH } from '@/lib/auth-routes';

import './globals.css';

interface GlobalErrorProps {
  error: Error & { digest?: string };
  /** Vuelve a pedir y renderizar la app (Next 16). */
  retry: () => void;
}

export default function GlobalError({ retry }: GlobalErrorProps) {
  return (
    <html lang="es" className="h-full">
      <body className="flex min-h-full flex-col bg-canvas font-sans text-ink antialiased">
        <title>Error · Talent Pipeline Tracker · Nexova</title>
        <main className="mx-auto flex w-full max-w-5xl flex-1 flex-col gap-6 px-4 py-8">
          <h1 className="text-xl font-semibold text-ink">Algo ha fallado</h1>
          <div
            role="alert"
            className="flex flex-col items-start gap-3 rounded-control border border-danger-ink/20 bg-danger-surface p-6 text-danger-ink"
          >
            <p className="text-sm font-semibold">No se pudo cargar el tracker</p>
            <p className="text-sm">Ha ocurrido un error inesperado. Puedes reintentarlo o volver a la página principal.</p>
            <div className="flex flex-wrap items-center gap-4">
              <Button variant="secondary" onClick={() => retry()}>
                Reintentar
              </Button>
              <a
                href={HOME_PATH}
                className="text-sm text-brand underline underline-offset-2 outline-none focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand"
              >
                Ir a la página principal
              </a>
            </div>
          </div>
        </main>
      </body>
    </html>
  );
}

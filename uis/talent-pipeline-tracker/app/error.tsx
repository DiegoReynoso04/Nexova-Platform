'use client';

// Límite de error de las rutas (Next 16, `app/error.tsx`). Captura los errores
// de render de cualquier vista: se muestra dentro del layout raíz (cabecera,
// sesión, guard y avisos siguen activos). Firma de props de Next 16.3:
// `{ error: Error & { digest?: string }; retry: () => void }` (también `reset`).
//
// Privacidad: el error no se muestra ni se registra. Nada de su mensaje, su
// `digest` ni su traza llega a la pantalla o a la consola; el texto es fijo.

import Link from 'next/link';

import { Button } from '@/components/ui/button';
import { HOME_PATH } from '@/lib/auth-routes';

interface RouteErrorProps {
  error: Error & { digest?: string };
  /** Vuelve a pedir y renderizar el segmento (Next 16). */
  retry: () => void;
}

export default function RouteError({ retry }: RouteErrorProps) {
  return (
    <main className="mx-auto flex w-full max-w-5xl flex-1 flex-col gap-6 px-4 py-8">
      <h1 className="text-xl font-semibold text-ink">Algo ha fallado</h1>
      <div
        role="alert"
        className="flex flex-col items-start gap-3 rounded-control border border-danger-ink/20 bg-danger-surface p-6 text-danger-ink"
      >
        <p className="text-sm font-semibold">No se pudo mostrar esta página</p>
        <p className="text-sm">Ha ocurrido un error inesperado. Puedes reintentarlo o volver al listado de candidaturas.</p>
        <div className="flex flex-wrap items-center gap-4">
          <Button variant="secondary" onClick={() => retry()}>
            Reintentar
          </Button>
          <Link
            href={HOME_PATH}
            className="text-sm text-brand underline underline-offset-2 outline-none focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand"
          >
            Ir al listado de candidaturas
          </Link>
        </div>
      </div>
    </main>
  );
}

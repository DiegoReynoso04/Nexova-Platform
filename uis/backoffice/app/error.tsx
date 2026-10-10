'use client';

// Límite de error de las rutas (Next 16, `app/error.tsx`). Captura los errores
// de render de cualquier página: se muestra dentro del layout raíz (cabecera,
// sesión y guard siguen activos). Firma de props de Next 16.3:
// `{ error: Error & { digest?: string }; retry: () => void }` (también `reset`).
//
// Privacidad: el error no se muestra ni se registra. Nada de su mensaje, su
// `digest` ni su traza llega a la pantalla o a la consola; el texto es fijo.

import Link from 'next/link';

import { Alert } from '@/components/ui/alert';
import { Button } from '@/components/ui/button';
import { HOME_PATH } from '@/lib/auth-routes';

interface RouteErrorProps {
  error: Error & { digest?: string };
  /** Vuelve a pedir y renderizar el segmento (Next 16). */
  retry: () => void;
}

export default function RouteError({ retry }: RouteErrorProps) {
  return (
    <section aria-labelledby="route-error-heading" className="flex flex-col gap-4">
      <h1 id="route-error-heading" className="text-lg font-semibold text-ink">
        Algo ha fallado
      </h1>
      <Alert variant="error" title="No se pudo mostrar esta página">
        <p>Ha ocurrido un error inesperado. Puedes reintentarlo o volver a la página principal.</p>
      </Alert>
      <div className="flex flex-wrap items-center gap-4">
        <Button onClick={() => retry()}>Reintentar</Button>
        <Link
          href={HOME_PATH}
          className="rounded-control text-sm font-medium text-brand underline underline-offset-2 outline-none focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand"
        >
          Ir a la página principal
        </Link>
      </div>
    </section>
  );
}

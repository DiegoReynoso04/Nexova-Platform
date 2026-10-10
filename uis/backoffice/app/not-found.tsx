// Página no encontrada (Next 16, `app/not-found.tsx`): rutas inexistentes y
// `notFound()`. Se renderiza dentro del layout raíz, así que el guard de
// sesión también la protege. Server Component: no necesita estado.

import Link from 'next/link';

import { HOME_PATH } from '@/lib/auth-routes';

export default function NotFound() {
  return (
    <section aria-labelledby="not-found-heading" className="flex flex-col gap-3 rounded-lg border border-border bg-surface p-6">
      <h1 id="not-found-heading" className="text-lg font-semibold text-ink">
        Página no encontrada
      </h1>
      <p className="text-sm text-ink-muted">
        La dirección que has abierto no existe en el backoffice. Puede que el enlace sea incorrecto o que la página se
        haya movido.
      </p>
      <p>
        <Link
          href={HOME_PATH}
          className="rounded-control text-sm font-medium text-brand underline underline-offset-2 outline-none focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand"
        >
          Ir a la página principal
        </Link>
      </p>
    </section>
  );
}

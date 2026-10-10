import Link from 'next/link';

import { HOME_PATH } from '@/lib/auth-routes';

// Página no encontrada raíz (Next 16, `app/not-found.tsx`): rutas que no
// existen. Una candidatura inexistente sigue usando su propio
// `app/candidates/[id]/not-found.tsx` (REQ-3). Se renderiza dentro del
// layout raíz, así que el guard de sesión también la protege.
export default function NotFound() {
  return (
    <main className="mx-auto flex w-full max-w-3xl flex-1 flex-col items-start gap-3 px-4 py-16">
      <h1 className="text-xl font-semibold text-ink">Página no encontrada</h1>
      <p className="text-sm text-ink-muted">
        La dirección que has abierto no existe en el tracker. Puede que el enlace sea incorrecto o que la página se haya
        movido.
      </p>
      <Link
        href={HOME_PATH}
        className="text-sm text-brand underline-offset-2 outline-none hover:underline focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand"
      >
        ← Volver al listado de candidaturas
      </Link>
    </main>
  );
}

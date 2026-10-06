import type { Metadata } from 'next';
import { Suspense } from 'react';

import { ResetPasswordView } from '@/components/auth/reset-password-view';

// Ruta abierta (lib/auth-routes.ts, OPEN_PATHS; AUTH-03): se abre desde el
// enlace del email, con o sin sesión. `no-referrer`: la URL lleva el token
// hasta que la vista lo quita. `Suspense`: la vista lee `?token=` con
// useSearchParams (obligatorio en el build).
export const metadata: Metadata = {
  title: 'Restablecer contraseña · Nexova',
  description: 'Elige una contraseña nueva para tu cuenta del backoffice de Nexova.',
  referrer: 'no-referrer',
};

export default function ResetPasswordPage() {
  return (
    <section aria-labelledby="reset-password-heading" className="mx-auto flex w-full max-w-md flex-col gap-4">
      <div className="flex flex-col gap-1">
        <h1 id="reset-password-heading" className="text-lg font-semibold text-ink">
          Restablecer contraseña
        </h1>
        <p className="text-sm text-ink-muted">Elige una contraseña nueva para tu cuenta.</p>
      </div>
      <Suspense>
        <ResetPasswordView />
      </Suspense>
    </section>
  );
}

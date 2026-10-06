'use client';

import { Suspense } from 'react';

import { ResetPasswordForm } from '@/components/auth/reset-password-form';

// Ruta abierta (lib/auth-routes.ts, OPEN_PATHS; AUTH-03): se abre desde el
// enlace del email, con o sin sesión. `Suspense`: el formulario lee `?token=`
// con useSearchParams (obligatorio en el build). El `<meta>` evita enviar la
// URL con el token como Referer mientras siga en la barra de direcciones.
export default function ResetPasswordPage() {
  return (
    <main className="mx-auto flex w-full max-w-md flex-1 flex-col gap-4 px-4 py-8">
      <meta name="referrer" content="no-referrer" />
      <div className="flex flex-col gap-1">
        <h1 className="text-lg font-semibold text-ink">Restablecer contraseña</h1>
        <p className="text-sm text-ink-muted">Elige una contraseña nueva para tu cuenta.</p>
      </div>
      <Suspense>
        <ResetPasswordForm />
      </Suspense>
    </main>
  );
}

import type { Metadata } from 'next';

import { ForgotPasswordView } from '@/components/auth/forgot-password-view';

// Ruta pública (lib/auth-routes.ts, AUTH-03). Server Component: exporta la
// metadata y renderiza el formulario, que es un Client Component.
export const metadata: Metadata = {
  title: 'Recuperar contraseña · Nexova',
  description: 'Solicita un enlace para restablecer la contraseña del backoffice de Nexova.',
};

export default function ForgotPasswordPage() {
  return (
    <section aria-labelledby="forgot-password-heading" className="mx-auto flex w-full max-w-md flex-col gap-4">
      <div className="flex flex-col gap-1">
        <h1 id="forgot-password-heading" className="text-lg font-semibold text-ink">
          ¿Olvidaste tu contraseña?
        </h1>
        <p className="text-sm text-ink-muted">
          Escribe el email de tu cuenta y te enviaremos un enlace para elegir una contraseña nueva.
        </p>
      </div>
      <ForgotPasswordView />
    </section>
  );
}

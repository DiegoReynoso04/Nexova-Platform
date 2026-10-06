'use client';

import { ForgotPasswordForm } from '@/components/auth/forgot-password-form';

// Ruta pública (lib/auth-routes.ts, AUTH-03).
export default function ForgotPasswordPage() {
  return (
    <main className="mx-auto flex w-full max-w-md flex-1 flex-col gap-4 px-4 py-8">
      <div className="flex flex-col gap-1">
        <h1 className="text-lg font-semibold text-ink">¿Olvidaste tu contraseña?</h1>
        <p className="text-sm text-ink-muted">
          Escribe el email de tu cuenta y te enviaremos un enlace para elegir una contraseña nueva.
        </p>
      </div>
      <ForgotPasswordForm />
    </main>
  );
}

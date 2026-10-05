'use client';

import { RegisterForm } from '@/components/auth/register-form';

// Ruta pública (lib/auth-routes.ts, AUTH-02).
export default function RegisterPage() {
  return (
    <main className="mx-auto flex w-full max-w-md flex-1 flex-col gap-4 px-4 py-8">
      <div className="flex flex-col gap-1">
        <h1 className="text-lg font-semibold text-ink">Crear cuenta</h1>
        <p className="text-sm text-ink-muted">Al terminar el registro se inicia la sesión automáticamente.</p>
      </div>
      <RegisterForm />
    </main>
  );
}

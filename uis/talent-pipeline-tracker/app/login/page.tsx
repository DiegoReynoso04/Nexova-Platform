'use client';

import { Suspense } from 'react';

import { LoginForm } from '@/components/auth/login-form';

// Ruta pública (lib/auth-routes.ts, AUTH-02). `Suspense`: el formulario lee
// `?reset=success` con useSearchParams (obligatorio en el build).
export default function LoginPage() {
  return (
    <main className="mx-auto flex w-full max-w-md flex-1 flex-col gap-4 px-4 py-8">
      <div className="flex flex-col gap-1">
        <h1 className="text-lg font-semibold text-ink">Iniciar sesión</h1>
        <p className="text-sm text-ink-muted">Entra con tu cuenta de Nexova para gestionar las candidaturas.</p>
      </div>
      <Suspense>
        <LoginForm />
      </Suspense>
    </main>
  );
}

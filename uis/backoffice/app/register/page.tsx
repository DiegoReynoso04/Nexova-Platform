import type { Metadata } from 'next';

import { RegisterView } from '@/components/auth/register-view';

// Ruta pública (lib/auth-routes.ts). Server Component: exporta la metadata y
// renderiza el formulario, que es un Client Component.
export const metadata: Metadata = {
  title: 'Crear cuenta · Nexova',
  description: 'Registro de usuarios del backoffice interno de Nexova Solutions.',
};

export default function RegisterPage() {
  return (
    <section aria-labelledby="register-heading" className="mx-auto flex w-full max-w-md flex-col gap-4">
      <div className="flex flex-col gap-1">
        <h1 id="register-heading" className="text-lg font-semibold text-ink">
          Crear cuenta
        </h1>
        <p className="text-sm text-ink-muted">Al terminar el registro se inicia la sesión automáticamente.</p>
      </div>
      <RegisterView />
    </section>
  );
}

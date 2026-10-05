import type { Metadata } from 'next';

import { LoginView } from '@/components/auth/login-view';

// Ruta pública (lib/auth-routes.ts). Server Component: exporta la metadata y
// renderiza el formulario, que es un Client Component.
export const metadata: Metadata = {
  title: 'Iniciar sesión · Nexova',
  description: 'Acceso al backoffice interno de Nexova Solutions.',
};

export default function LoginPage() {
  return (
    <section aria-labelledby="login-heading" className="mx-auto flex w-full max-w-md flex-col gap-4">
      <div className="flex flex-col gap-1">
        <h1 id="login-heading" className="text-lg font-semibold text-ink">
          Iniciar sesión
        </h1>
        <p className="text-sm text-ink-muted">Entra con tu email y tu contraseña para usar las herramientas internas.</p>
      </div>
      <LoginView />
    </section>
  );
}

import type { Metadata } from 'next';
import Link from 'next/link';

import { ChangePasswordView } from '@/components/auth/change-password-view';
import { PROFILE_PATH } from '@/lib/auth-routes';

// Ruta protegida (guard del layout raíz; AUTH-03). Server Component: exporta
// la metadata y renderiza el formulario, que es un Client Component.
export const metadata: Metadata = {
  title: 'Cambiar contraseña · Nexova',
  description: 'Cambia la contraseña de tu cuenta del backoffice de Nexova.',
};

export default function ChangePasswordPage() {
  return (
    <section aria-labelledby="change-password-heading" className="flex w-full max-w-md flex-col gap-4">
      <div className="flex flex-col gap-1">
        <h1 id="change-password-heading" className="text-lg font-semibold text-ink">
          Cambiar contraseña
        </h1>
        <p className="text-sm text-ink-muted">Confirma tu contraseña actual y elige una nueva.</p>
        <p className="text-sm">
          <Link href={PROFILE_PATH} className="font-medium text-brand underline underline-offset-4">
            Volver a mi perfil
          </Link>
        </p>
      </div>
      <ChangePasswordView />
    </section>
  );
}

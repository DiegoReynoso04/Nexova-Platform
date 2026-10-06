'use client';

import Link from 'next/link';

import { ChangePasswordForm } from '@/components/auth/change-password-form';
import { PROFILE_PATH } from '@/lib/auth-routes';

// Ruta protegida (guard del layout raíz, AUTH-03).
export default function ChangePasswordPage() {
  return (
    <main className="mx-auto flex w-full max-w-md flex-1 flex-col gap-4 px-4 py-8">
      <div className="flex flex-col gap-1">
        <h1 className="text-lg font-semibold text-ink">Cambiar contraseña</h1>
        <p className="text-sm text-ink-muted">Confirma tu contraseña actual y elige una nueva.</p>
        <p className="text-sm">
          <Link href={PROFILE_PATH} className="font-medium text-brand underline underline-offset-4">
            Volver a mi perfil
          </Link>
        </p>
      </div>
      <ChangePasswordForm />
    </main>
  );
}

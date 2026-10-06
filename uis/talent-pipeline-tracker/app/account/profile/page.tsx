'use client';

import Link from 'next/link';

import { ProfileView } from '@/components/auth/profile-view';
import { CHANGE_PASSWORD_PATH } from '@/lib/auth-routes';

// Ruta protegida (guard del layout raíz, AUTH-02).
export default function ProfilePage() {
  return (
    <main className="mx-auto flex w-full max-w-3xl flex-1 flex-col gap-6 px-4 py-8">
      <div className="flex flex-col gap-1">
        <h1 className="text-lg font-semibold text-ink">Mi perfil</h1>
        <p className="text-sm text-ink-muted">Consulta los datos de tu cuenta y actualiza tu nombre y tus datos de contacto.</p>
        <p className="text-sm">
          <Link href={CHANGE_PASSWORD_PATH} className="font-medium text-brand underline underline-offset-4">
            Cambiar contraseña
          </Link>
        </p>
      </div>
      <ProfileView />
    </main>
  );
}

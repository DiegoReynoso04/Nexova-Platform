import type { Metadata } from 'next';
import Link from 'next/link';

import { ProfileView } from '@/components/auth/profile-view';
import { CHANGE_PASSWORD_PATH } from '@/lib/auth-routes';

// Ruta protegida (guard del layout raíz). Server Component: exporta la
// metadata y renderiza la vista, que es un Client Component.
export const metadata: Metadata = {
  title: 'Mi perfil · Nexova',
  description: 'Datos de tu cuenta y de contacto en el backoffice de Nexova.',
};

export default function ProfilePage() {
  return (
    <>
      <div className="flex flex-col gap-2">
        <h1 className="text-lg font-semibold text-ink">Mi perfil</h1>
        <p className="text-sm text-ink-muted">Consulta los datos de tu cuenta y actualiza tu nombre y tus datos de contacto.</p>
        <p className="text-sm">
          <Link href={CHANGE_PASSWORD_PATH} className="font-medium text-brand underline underline-offset-4">
            Cambiar contraseña
          </Link>
        </p>
      </div>
      <ProfileView />
    </>
  );
}

import type { Metadata } from 'next';

import { ProfileView } from '@/components/auth/profile-view';

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
      </div>
      <ProfileView />
    </>
  );
}

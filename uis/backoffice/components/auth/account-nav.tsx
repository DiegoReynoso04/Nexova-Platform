'use client';

import { useRouter } from 'next/navigation';

import { Button } from '@/components/ui/button';
import { NavLink } from '@/components/ui/nav-link';
import { LOGIN_PATH, PROFILE_PATH, REGISTER_PATH } from '@/lib/auth-routes';

import { useSession } from './session-provider';

// Navegación de la cabecera según la sesión: con sesión válida, las vistas
// protegidas, el perfil y el logout; sin sesión, solo acceso y registro.
export function AccountNav() {
  const session = useSession();
  const router = useRouter();

  function handleLogout() {
    session.logout();
    router.replace(LOGIN_PATH);
  }

  if (session.status === 'authenticated') {
    return (
      <nav aria-label="Principal" className="flex flex-wrap items-center gap-4">
        <NavLink href="/incidents">Análisis de incidentes</NavLink>
        <NavLink href="/suppliers">Proveedores</NavLink>
        <NavLink href={PROFILE_PATH}>Mi perfil</NavLink>
        <span className="text-xs text-ink-muted" title="Sesión iniciada">
          {session.user.email}
        </span>
        <Button variant="secondary" onClick={handleLogout} className="px-3 py-1">
          Cerrar sesión
        </Button>
      </nav>
    );
  }

  if (session.status === 'anonymous') {
    return (
      <nav aria-label="Acceso" className="flex flex-wrap items-center gap-4">
        <NavLink href={LOGIN_PATH}>Iniciar sesión</NavLink>
        <NavLink href={REGISTER_PATH}>Crear cuenta</NavLink>
      </nav>
    );
  }

  return null;
}

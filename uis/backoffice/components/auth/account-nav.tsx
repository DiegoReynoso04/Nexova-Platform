'use client';

import { usePathname, useRouter } from 'next/navigation';

import { Button } from '@/components/ui/button';
import { NavLink, NavLinkPlaceholders } from '@/components/ui/nav-link';
import { headerNavMode, LOGIN_PATH, PROFILE_PATH, REGISTER_PATH } from '@/lib/auth-routes';
import { INCIDENT_MANAGER_PATH, NEW_INCIDENT_PATH } from '@/lib/incident-manager-routes';
import { INVENTORY_PATH, INVENTORY_PRODUCTS_PATH } from '@/lib/inventory-routes';

import { useSession } from './session-provider';

const SESSION_NAV_CLASSES = 'flex flex-wrap items-center gap-4';

// Enlaces de la navegación con sesión. Con `placeholder`, los mismos textos y
// clases como <span>, sin `href` (ver NavLinkPlaceholders).
function SessionLinks({ placeholder = false }: { placeholder?: boolean }) {
  const links = (
    <>
      <NavLink href="/incidents">Análisis de incidentes</NavLink>
      <NavLink href="/suppliers">Proveedores</NavLink>
      <NavLink href={INCIDENT_MANAGER_PATH}>Incidencias</NavLink>
      <NavLink href={NEW_INCIDENT_PATH}>Registrar incidencia</NavLink>
      {/* Un solo enlace: las cuatro páginas del inventario tienen su propia subnavegación. */}
      <NavLink href={INVENTORY_PRODUCTS_PATH} activePrefix={INVENTORY_PATH}>
        Inventario
      </NavLink>
      <NavLink href={PROFILE_PATH}>Mi perfil</NavLink>
    </>
  );
  return placeholder ? <NavLinkPlaceholders>{links}</NavLinkPlaceholders> : links;
}

// Navegación de la cabecera según la sesión (headerNavMode): con sesión válida,
// las vistas protegidas, el perfil y el logout; sin sesión, solo acceso y
// registro. Mientras se valida la sesión en una ruta protegida, el hueco de la
// navegación con sesión, invisible e inerte: así la cabecera ya tiene su altura
// final desde el HTML del servidor y no empuja la página al llegar `/auth/me`.
export function AccountNav() {
  const session = useSession();
  const pathname = usePathname();
  const router = useRouter();
  const mode = headerNavMode(pathname, session.status);

  function handleLogout() {
    session.logout();
    router.replace(LOGIN_PATH);
  }

  if (mode === 'session' && session.status === 'authenticated') {
    return (
      <nav aria-label="Principal" className={SESSION_NAV_CLASSES}>
        <SessionLinks />
        <span className="text-xs text-ink-muted" title="Sesión iniciada">
          {session.user.email}
        </span>
        <Button variant="secondary" onClick={handleLogout} className="px-3 py-1">
          Cerrar sesión
        </Button>
      </nav>
    );
  }

  if (mode === 'reserved') {
    // Fuera del árbol de accesibilidad y del foco. El email aún no se conoce:
    // un hueco de ancho parecido. El botón es el mismo, deshabilitado y sin acción.
    return (
      <div aria-hidden="true" inert className={`invisible ${SESSION_NAV_CLASSES}`}>
        <SessionLinks placeholder />
        <span className="inline-block h-4 w-40" />
        <Button variant="secondary" disabled tabIndex={-1} className="px-3 py-1">
          Cerrar sesión
        </Button>
      </div>
    );
  }

  if (mode === 'access') {
    return (
      <nav aria-label="Acceso" className="flex flex-wrap items-center gap-4">
        <NavLink href={LOGIN_PATH}>Iniciar sesión</NavLink>
        <NavLink href={REGISTER_PATH}>Crear cuenta</NavLink>
      </nav>
    );
  }

  return null;
}

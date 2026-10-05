'use client';

import Link from 'next/link';
import { useRouter } from 'next/navigation';

import { Button } from '@/components/ui/button';
import { HOME_PATH, LOGIN_PATH, PROFILE_PATH, REGISTER_PATH } from '@/lib/auth-routes';

import { useSession } from './session-provider';

const LINK_CLASSES =
  'rounded-control px-1 text-sm font-medium text-ink-muted outline-none hover:text-brand focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand';

// Cabecera (AUTH-02): con sesión válida muestra el acceso al perfil y el
// logout; sin sesión, solo los enlaces de acceso y registro.
export function AppHeader() {
  const session = useSession();
  const router = useRouter();

  function handleLogout() {
    session.logout();
    router.replace(LOGIN_PATH);
  }

  return (
    <header className="border-b border-border bg-surface">
      <div className="mx-auto flex max-w-5xl flex-wrap items-center justify-between gap-x-6 gap-y-2 px-4 py-3">
        <Link
          href={HOME_PATH}
          className="rounded-control text-sm font-semibold tracking-tight text-ink outline-none focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand"
        >
          Nexova <span className="text-ink-muted">· Talent Pipeline Tracker</span>
        </Link>
        {session.status === 'authenticated' && (
          <nav aria-label="Cuenta" className="flex flex-wrap items-center gap-4">
            <Link href={PROFILE_PATH} className={LINK_CLASSES}>
              Mi perfil
            </Link>
            <span className="text-xs text-ink-muted">{session.user.email}</span>
            <Button variant="secondary" onClick={handleLogout} className="px-3 py-1">
              Cerrar sesión
            </Button>
          </nav>
        )}
        {session.status === 'anonymous' && (
          <nav aria-label="Acceso" className="flex flex-wrap items-center gap-4">
            <Link href={LOGIN_PATH} className={LINK_CLASSES}>
              Iniciar sesión
            </Link>
            <Link href={REGISTER_PATH} className={LINK_CLASSES}>
              Crear cuenta
            </Link>
          </nav>
        )}
      </div>
    </header>
  );
}

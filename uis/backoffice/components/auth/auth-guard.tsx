'use client';

import { usePathname, useRouter } from 'next/navigation';
import { useEffect, type ReactNode } from 'react';

import { Alert } from '@/components/ui/alert';
import { Button } from '@/components/ui/button';
import { LoadingSpinner } from '@/components/ui/loading-spinner';
import { HOME_PATH, LOGIN_PATH, routeAccess } from '@/lib/auth-routes';

import { useSession } from './session-provider';

// Guard global (layout raíz): protege todas las vistas salvo las públicas
// y abiertas de lib/auth-routes.ts (/login, /register, /forgot-password,
// /reset-password). Sin token, o cuando un 401 lo borra,
// redirige a /login; la vista protegida no se muestra hasta que `GET /auth/me`
// confirma la sesión.
export function AuthGuard({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const session = useSession();
  const access = routeAccess(pathname, session.status);

  useEffect(() => {
    if (access === 'redirect_login') router.replace(LOGIN_PATH);
    if (access === 'redirect_home') router.replace(HOME_PATH);
  }, [access, router]);

  if (access === 'render') return <>{children}</>;

  if (access === 'error' && session.status === 'error') {
    return (
      <div className="flex flex-col gap-3">
        <Alert variant="error" title="No se pudo comprobar la sesión">
          <p>La API no respondió al validar tu sesión. Comprueba que está en marcha e inténtalo de nuevo.</p>
        </Alert>
        <div className="flex flex-wrap gap-2">
          <Button onClick={session.retry}>Reintentar</Button>
          <Button variant="secondary" onClick={session.logout}>
            Cerrar sesión
          </Button>
        </div>
      </div>
    );
  }

  const label = access === 'wait' ? 'Comprobando la sesión…' : 'Redirigiendo…';
  return (
    <div className="flex items-center gap-2 text-sm text-ink-muted">
      <LoadingSpinner />
      <span role="status">{label}</span>
    </div>
  );
}

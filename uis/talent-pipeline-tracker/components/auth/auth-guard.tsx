'use client';

import { usePathname, useRouter } from 'next/navigation';
import { useEffect, type ReactNode } from 'react';

import { Button } from '@/components/ui/button';
import { LoadingSpinner } from '@/components/ui/loading-spinner';
import { sessionErrorCopy } from '@/hooks/use-auth-session';
import { HOME_PATH, LOGIN_PATH, routeAccess } from '@/lib/auth-routes';

import { useSession } from './session-provider';

// Guard global (layout raíz, AUTH-02): protege todas las vistas salvo las
// públicas y abiertas de lib/auth-routes.ts (/login, /register,
// /forgot-password, /reset-password). Sin token, o cuando un 401 lo borra,
// redirige a /login; ninguna vista protegida se muestra (ni pide datos a la
// API de 4Geeks) hasta que `GET /auth/me` confirma la sesión.
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

  if (access === 'error' && (session.status === 'error' || session.status === 'retrying')) {
    // Durante el reintento se mantiene el aviso y «Reintentar» muestra la carga.
    const { title, body } = sessionErrorCopy(session.kind);
    const retrying = session.status === 'retrying';
    return (
      <main className="mx-auto flex w-full max-w-5xl flex-1 flex-col gap-6 px-4 py-8">
        <div
          role="alert"
          className="flex flex-col items-start gap-3 rounded-control border border-danger-ink/20 bg-danger-surface p-6 text-danger-ink"
        >
          <p className="text-sm font-semibold">{title}</p>
          <p className="text-sm">{body}</p>
          <div className="flex flex-wrap gap-2">
            <Button variant="secondary" onClick={session.retry} isLoading={retrying}>
              {retrying ? 'Reintentando…' : 'Reintentar'}
            </Button>
            <Button variant="secondary" onClick={session.logout}>
              Cerrar sesión
            </Button>
          </div>
        </div>
      </main>
    );
  }

  return (
    <main className="mx-auto flex w-full max-w-5xl flex-1 items-start px-4 py-8">
      <LoadingSpinner label={access === 'wait' ? 'Comprobando la sesión…' : 'Redirigiendo…'} />
    </main>
  );
}

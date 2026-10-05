'use client';

import { createContext, useContext, type ReactNode } from 'react';

import { useAuthSession, type AuthSession } from '@/hooks/use-auth-session';

// Una única sesión para todo el backoffice: la crea el layout raíz (que no se
// desmonta al navegar), así que el token se valida una vez y no en cada vista.
const SessionContext = createContext<AuthSession | null>(null);

export function SessionProvider({ children }: { children: ReactNode }) {
  const session = useAuthSession();
  return <SessionContext.Provider value={session}>{children}</SessionContext.Provider>;
}

export function useSession(): AuthSession {
  const session = useContext(SessionContext);
  if (session === null) throw new Error('useSession must be used inside <SessionProvider>');
  return session;
}

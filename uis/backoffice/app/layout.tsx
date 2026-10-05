import type { Metadata } from 'next';
import Link from 'next/link';

import { AccountNav } from '@/components/auth/account-nav';
import { AuthGuard } from '@/components/auth/auth-guard';
import { SessionProvider } from '@/components/auth/session-provider';
import './globals.css';

export const metadata: Metadata = {
  title: 'Backoffice · Nexova',
  description: 'Panel interno de Nexova Solutions — punto de entrada para las herramientas de operación de la empresa.',
};

export default function RootLayout({ children }: LayoutProps<'/'>) {
  return (
    <html lang="es" className="h-full">
      <body className="flex min-h-full flex-col bg-canvas font-sans text-ink antialiased">
        {/* AUTH-02: una sesión para toda la app; el guard protege todas las vistas salvo /login y /register. */}
        <SessionProvider>
          <header className="border-b border-border bg-surface">
            <div className="mx-auto flex max-w-4xl flex-wrap items-center justify-between gap-x-6 gap-y-2 px-4 py-4">
              <Link
                href="/"
                className="rounded-control text-sm font-semibold tracking-tight text-ink outline-none focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand"
              >
                Nexova <span className="text-ink-muted">· Backoffice</span>
              </Link>
              <AccountNav />
            </div>
          </header>
          <main className="mx-auto flex w-full max-w-4xl flex-1 flex-col gap-8 px-4 py-8">
            <AuthGuard>{children}</AuthGuard>
          </main>
        </SessionProvider>
      </body>
    </html>
  );
}

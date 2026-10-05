import type { Metadata } from 'next';
import { AppHeader } from '@/components/auth/app-header';
import { AuthGuard } from '@/components/auth/auth-guard';
import { SessionProvider } from '@/components/auth/session-provider';
import { ToastProvider } from '@/components/ui/toast-notification';
import './globals.css';

export const metadata: Metadata = {
  title: 'Talent Pipeline Tracker · Nexova',
  description: 'Gestión interna de candidaturas — Operaciones de Selección, Nexova Solutions.',
};

export default function RootLayout({ children }: LayoutProps<'/'>) {
  return (
    <html lang="es" className="h-full">
      <body className="flex min-h-full flex-col bg-canvas font-sans text-ink antialiased">
        <ToastProvider>
          {/* AUTH-02: una sesión para toda la app; el guard protege todas las vistas salvo /login y /register. */}
          <SessionProvider>
            <AppHeader />
            <AuthGuard>{children}</AuthGuard>
          </SessionProvider>
        </ToastProvider>
      </body>
    </html>
  );
}

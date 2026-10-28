'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { createContext, useContext, type ReactNode } from 'react';

export interface NavLinkProps {
  href: string;
  children: ReactNode;
  /**
   * Marca el enlace como actual en cualquier ruta bajo este prefijo (p. ej.
   * «Inventario» en las cuatro páginas de `/inventory`). Por defecto, solo en `href`.
   */
  activePrefix?: string;
}

// Dentro de <NavLinkPlaceholders>, cada NavLink se pinta como un <span> con las
// mismas clases y el mismo texto, sin `href`: ocupa lo mismo que el enlace,
// pero Next no lo precarga y el HTML no lleva el enlace (cabecera reservada de
// components/auth/account-nav.tsx).
const PlaceholderContext = createContext(false);

export function NavLinkPlaceholders({ children }: { children: ReactNode }) {
  return <PlaceholderContext.Provider value={true}>{children}</PlaceholderContext.Provider>;
}

function isUnder(pathname: string, prefix: string): boolean {
  return pathname === prefix || pathname.startsWith(`${prefix}/`);
}

// Enlace de navegación que marca la página actual con aria-current (y con un
// subrayado, para no depender solo del color). usePathname exige cliente.
export function NavLink({ href, children, activePrefix }: NavLinkProps) {
  const pathname = usePathname();
  const placeholder = useContext(PlaceholderContext);
  const isCurrent = activePrefix === undefined ? pathname === href : isUnder(pathname, activePrefix);
  const className = `rounded-control px-1 text-sm font-medium outline-none hover:text-brand focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand ${
    isCurrent ? 'text-ink underline decoration-2 underline-offset-8' : 'text-ink-muted'
  }`;

  if (placeholder) return <span className={className}>{children}</span>;

  return (
    <Link href={href} aria-current={isCurrent ? 'page' : undefined} className={className}>
      {children}
    </Link>
  );
}

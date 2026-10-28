import type { ReactNode } from 'react';

export interface TableScrollProps {
  /** La <table> (o lo que deba desplazarse en horizontal). */
  children: ReactNode;
  /** Borde, fondo y esquinas de las tablas de datos (listados). Sin él, solo el desplazamiento. */
  framed?: boolean;
  /** Clases extra del contenedor (p. ej. el margen superior). */
  className?: string;
}

// Contenedor con scroll horizontal de las tablas. `relative`: los elementos
// `sr-only` de dentro (position: absolute) toman este contenedor como bloque
// contenedor y quedan recortados por su overflow. Sin él, ensanchaban el
// documento en móvil (scroll horizontal de toda la página a 375 px).
export function TableScroll({ children, framed = false, className = '' }: TableScrollProps) {
  const frame = framed ? 'rounded-lg border border-border bg-surface' : '';
  return <div className={`relative overflow-x-auto ${frame} ${className}`}>{children}</div>;
}

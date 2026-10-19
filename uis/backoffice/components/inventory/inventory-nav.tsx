import { NavLink } from '@/components/ui/nav-link';
import {
  INVENTORY_INBOUND_PATH,
  INVENTORY_ORDERS_PATH,
  INVENTORY_OUTBOUND_PATH,
  INVENTORY_PRODUCTS_PATH,
} from '@/lib/inventory-routes';

// Subnavegación común a las cuatro páginas del inventario (app/inventory/layout.tsx).
// NavLink marca la página activa con aria-current. Etiquetas del CONTEXT.
const INVENTORY_LINKS: readonly { href: string; label: string }[] = [
  { href: INVENTORY_PRODUCTS_PATH, label: 'Activos' },
  { href: INVENTORY_INBOUND_PATH, label: 'Entrada de activos' },
  { href: INVENTORY_OUTBOUND_PATH, label: 'Salida de activos' },
  { href: INVENTORY_ORDERS_PATH, label: 'Historial' },
];

export function InventoryNav() {
  return (
    <nav aria-label="Inventario" className="flex flex-wrap gap-x-4 gap-y-2 border-b border-border pb-3">
      {INVENTORY_LINKS.map((link) => (
        <NavLink key={link.href} href={link.href}>
          {link.label}
        </NavLink>
      ))}
    </nav>
  );
}

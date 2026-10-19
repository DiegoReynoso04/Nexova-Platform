import { InventoryNav } from '@/components/inventory/inventory-nav';

// Layout común a las páginas del inventario: título de la sección y la
// subnavegación (Activos · Entrada de activos · Salida de activos · Historial).
// La protección la da el guard global del layout raíz: estas rutas no son públicas.
export default function InventoryLayout({ children }: LayoutProps<'/inventory'>) {
  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-col gap-3">
        <p className="text-xs font-semibold uppercase tracking-wide text-ink-muted">Inventario</p>
        <InventoryNav />
      </div>
      {children}
    </div>
  );
}

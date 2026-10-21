import { ORDER_TYPE_BADGES } from '@/lib/order-format';
import type { OrderType } from '@/types/inventory';

// Insignia del tipo de orden del Historial: color, icono y texto distintos
// para «Entrada» y «Salida» (se distinguen también sin ver los colores).

const TYPE_CLASSES: Readonly<Record<OrderType, string>> = {
  inbound: 'border-success-ink/30 bg-success-surface text-success-ink',
  outbound: 'border-info-ink/30 bg-info-surface text-info-ink',
};

export interface OrderTypeBadgeProps {
  type: OrderType;
}

export function OrderTypeBadge({ type }: OrderTypeBadgeProps) {
  const { label, icon } = ORDER_TYPE_BADGES[type];
  return (
    <span className={`inline-flex items-center gap-1 whitespace-nowrap rounded-full border px-2 py-0.5 text-xs font-semibold ${TYPE_CLASSES[type]}`}>
      <span aria-hidden="true">{icon}</span>
      {label}
    </span>
  );
}

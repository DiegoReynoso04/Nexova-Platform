import { STOCK_LEVEL_LABELS, stockLevel, type StockLevel } from '@/lib/stock-level';

// Indicador del nivel de stock (umbrales en lib/stock-level.ts). Color, icono
// y texto: el nivel se entiende también sin distinguir colores.

const LEVEL_CLASSES: Readonly<Record<StockLevel, string>> = {
  out: 'border-danger-ink/30 bg-danger-surface text-danger-ink',
  low: 'border-warning-ink/30 bg-warning-surface text-warning-ink',
  ok: 'border-success-ink/30 bg-success-surface text-success-ink',
};

const LEVEL_ICONS: Readonly<Record<StockLevel, string>> = {
  out: '✕',
  low: '!',
  ok: '✓',
};

export interface StockLevelBadgeProps {
  currentStock: number;
}

export function StockLevelBadge({ currentStock }: StockLevelBadgeProps) {
  const level = stockLevel(currentStock);
  return (
    <span
      className={`inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-xs font-semibold ${LEVEL_CLASSES[level]}`}
    >
      <span aria-hidden="true">{LEVEL_ICONS[level]}</span>
      {STOCK_LEVEL_LABELS[level]}
    </span>
  );
}

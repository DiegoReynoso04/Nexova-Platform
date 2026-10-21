import { Alert } from '@/components/ui/alert';
import { inventoryErrorCopy } from '@/lib/inventory-error-copy';
import type { InventoryUiError } from '@/types/inventory';

// Aviso de error del inventario. Los textos salen de lib/inventory-error-copy.ts.
// React escapa el texto: el `detail` de la API nunca se interpreta como HTML.

export interface InventoryErrorProps {
  error: InventoryUiError;
}

export function InventoryError({ error }: InventoryErrorProps) {
  const { title, body } = inventoryErrorCopy(error);
  return (
    <Alert variant="error" title={title}>
      <p>{body}</p>
    </Alert>
  );
}

import type { FieldMessage } from '@/lib/inventory-form-errors';

// Mensajes junto a un campo del formulario: el texto propio en español y,
// debajo, en texto secundario, el `msg` de la API cuando lo hay (opción 3 de
// los 422). Todo como texto plano: React lo escapa.

export interface FieldMessagesProps {
  /** Id que el campo enlaza con `aria-describedby`. */
  id: string;
  messages: readonly FieldMessage[];
  /** Se anuncia al aparecer (`role="alert"`): p. ej., el 400 de stock insuficiente junto a Cantidad. */
  alert?: boolean;
}

export function FieldMessages({ id, messages, alert = false }: FieldMessagesProps) {
  if (messages.length === 0) return null;
  return (
    <div id={id} role={alert ? 'alert' : undefined} className="flex flex-col gap-0.5">
      {messages.map((item, index) => (
        <div key={index}>
          <p className="text-xs font-medium text-danger-ink">{item.message}</p>
          {item.apiMessage !== undefined && <p className="text-xs text-ink-muted">Mensaje de la API: {item.apiMessage}</p>}
        </div>
      ))}
    </div>
  );
}

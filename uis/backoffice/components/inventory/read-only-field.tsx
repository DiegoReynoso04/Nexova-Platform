import type { ReactNode } from 'react';

import type { FieldMessage } from '@/lib/inventory-form-errors';

import { FieldMessages } from './field-messages';

// Valor de solo lectura de los formularios del inventario (Oficina y, en la
// salida, Stock actual). Es un <output> asociado a su etiqueta, con fondo
// atenuado y sin borde de campo: no se confunde con un control editable.

export interface ReadOnlyFieldProps {
  id: string;
  label: string;
  /** El valor; `null` muestra `placeholder`. */
  value: ReactNode | null;
  placeholder: string;
  help?: string;
  messages?: readonly FieldMessage[];
}

export function ReadOnlyField({ id, label, value, placeholder, help, messages = [] }: ReadOnlyFieldProps) {
  const helpId = `${id}-help`;
  const messagesId = `${id}-messages`;
  const describedBy = [help === undefined ? null : helpId, messages.length > 0 ? messagesId : null].filter((item) => item !== null).join(' ');

  return (
    <div className="flex flex-col gap-1">
      <label htmlFor={id} className="text-sm font-medium text-ink">
        {label}
      </label>
      <output id={id} aria-describedby={describedBy === '' ? undefined : describedBy} className="rounded-control bg-canvas px-3 py-2 text-sm text-ink">
        {value === null ? <span className="text-ink-muted italic">{placeholder}</span> : value}
      </output>
      {help !== undefined && (
        <p id={helpId} className="text-xs text-ink-muted">
          {help}
        </p>
      )}
      <FieldMessages id={messagesId} messages={messages} />
    </div>
  );
}

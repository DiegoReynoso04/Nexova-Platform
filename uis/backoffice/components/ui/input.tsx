import { useId, type InputHTMLAttributes } from 'react';

export interface InputProps extends InputHTMLAttributes<HTMLInputElement> {
  label: string;
  /** Mensaje de error del campo; `null`/`undefined` = sin error. */
  error?: string | null;
  /** Texto de ayuda bajo el campo. */
  hint?: string;
}

// <label>/<input> reales asociados por id (patrón de
// uis/talent-pipeline-tracker/components/ui/input.tsx). aria-invalid y
// aria-describedby enlazan el error y la ayuda con el campo.
export function Input({ label, error, hint, id, className = '', ...props }: InputProps) {
  const generatedId = useId();
  const inputId = id ?? generatedId;
  const hasError = error !== undefined && error !== null && error !== '';
  const errorId = hasError ? `${inputId}-error` : undefined;
  const hintId = hint !== undefined ? `${inputId}-hint` : undefined;
  const describedBy = [errorId, hintId].filter((value) => value !== undefined).join(' ') || undefined;

  return (
    <div className="flex flex-col gap-1">
      <label htmlFor={inputId} className="text-sm font-medium text-ink">
        {label}
      </label>
      <input
        id={inputId}
        aria-invalid={hasError || undefined}
        aria-describedby={describedBy}
        className={`w-full rounded-control border bg-surface px-3 py-2 text-sm text-ink outline-none focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand ${
          hasError ? 'border-danger-ink' : 'border-border'
        } ${className}`}
        {...props}
      />
      {hint !== undefined && (
        <p id={hintId} className="text-xs text-ink-muted">
          {hint}
        </p>
      )}
      {hasError && (
        <p id={errorId} className="text-sm text-danger-ink">
          {error}
        </p>
      )}
    </div>
  );
}

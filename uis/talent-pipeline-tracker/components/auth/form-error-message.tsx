// Error general de un formulario de cuenta (los de campo van junto a cada Input).
export function FormErrorMessage({ message }: { message: string | null }) {
  if (message === null) return null;
  return (
    <p
      role="alert"
      className="rounded-control border border-danger-ink/20 bg-danger-surface px-4 py-3 text-sm text-danger-ink"
    >
      {message}
    </p>
  );
}

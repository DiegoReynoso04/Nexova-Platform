// Identidad de la sesión para la telemetría (ticket de captura, D8): `userId`
// (`sub`) y `sessionId` (`sid`) salen del JWT que ya guarda lib/auth-token.ts.
// No se guarda nada nuevo en el navegador: se leen del token en cada evento,
// así que sobreviven a la recarga y coinciden con los que ve la API.
//
// Solo se decodifica el payload (base64url + JSON); la firma la comprueba la
// API. El JSON va a `normalizeTokenIdentity`, la frontera de confianza.

import { readAuthToken } from '@/lib/auth-token';
import { normalizeTokenIdentity, type TokenIdentity } from '@/services/normalizers';

const ANONYMOUS: TokenIdentity = { userId: null, sessionId: null };

function decodeBase64Url(segment: string): string {
  const base64 = segment.replaceAll('-', '+').replaceAll('_', '/');
  const padded = base64 + '='.repeat((4 - (base64.length % 4)) % 4);
  const binary = atob(padded);
  const bytes = Uint8Array.from(binary, (character) => character.charCodeAt(0));
  return new TextDecoder().decode(bytes);
}

/** Identidad del token dado, o anónima si no hay token o no se puede leer. */
export function identityFromToken(token: string | null): TokenIdentity {
  if (token === null) return ANONYMOUS;
  const payload = token.split('.')[1];
  if (payload === undefined || payload === '') return ANONYMOUS;
  try {
    return normalizeTokenIdentity(JSON.parse(decodeBase64Url(payload)));
  } catch {
    return ANONYMOUS;
  }
}

/** Identidad de la sesión actual (token de lib/auth-token.ts). */
export function readSessionIdentity(): TokenIdentity {
  return identityFromToken(readAuthToken());
}

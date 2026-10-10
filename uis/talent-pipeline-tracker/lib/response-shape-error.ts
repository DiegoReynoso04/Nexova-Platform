// Error de los normalizadores (services/normalizers.ts, §3.1): una respuesta
// 2xx que no cumple el contrato. Su mensaje es descriptivo para depurar (campo
// y tipo recibido, nunca el valor), pero no se muestra al usuario: la UI usa
// describeApiError (lib/api-client.ts), que lo trata como respuesta ilegible.
//
// Módulo propio y sin efectos: los normalizadores no dependen de
// lib/api-client.ts, que falla al importarse sin variables de entorno (§3.2).

export class ResponseShapeError extends Error {
  constructor(message: string) {
    super(message);
    this.name = 'ResponseShapeError';
  }
}

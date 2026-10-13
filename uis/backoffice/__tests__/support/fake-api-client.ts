// Cliente HTTP falso que cumple la interfaz `ApiClient`: responde según
// "MÉTODO /ruta" y registra cada llamada. Así los tests del servicio prueban su
// lógica (validación, qué se guarda, traducción de errores) sin transporte real.

import type { ApiClient, ApiResponse, JsonValue, RequestOptions, ResponseHandler } from '@/lib/api-client';

export interface FakeReply {
  status: number;
  body?: JsonValue;
}

export type Reply = FakeReply | Error;

export interface RecordedCall {
  key: string;
  body: JsonValue | URLSearchParams | FormData | undefined;
  options: RequestOptions;
}

function response({ status, body }: FakeReply): ApiResponse {
  return {
    status,
    header: () => null,
    json: async <T>(parse: (value: JsonValue) => T) => parse(body ?? null),
    blob: async () => new Blob(),
  };
}

export function createFakeApiClient(replies: Record<string, Reply>): { client: ApiClient; calls: RecordedCall[] } {
  const calls: RecordedCall[] = [];

  function send<T>(
    method: string,
    path: string,
    body: RecordedCall['body'],
    options: RequestOptions,
    handle: ResponseHandler<T>
  ): Promise<T> {
    const key = `${method} ${path}`;
    calls.push({ key, body, options });
    const reply = replies[key];
    if (reply === undefined) throw new Error(`ruta no prevista: ${key}`);
    if (reply instanceof Error) return Promise.reject(reply);
    return handle(response(reply));
  }

  const client: ApiClient = {
    get: (path, options, handle) => send('GET', path, undefined, options, handle),
    postForm: (path, form, options, handle) => send('POST', path, form, options, handle),
    postJson: (path, body, options, handle) => send('POST', path, body, options, handle),
    patchJson: (path, body, options, handle) => send('PATCH', path, body, options, handle),
    putJson: (path, body, options, handle) => send('PUT', path, body, options, handle),
  };
  return { client, calls };
}

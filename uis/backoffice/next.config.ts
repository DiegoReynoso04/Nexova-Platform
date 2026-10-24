import type { NextConfig } from "next";

// Docker (#infra-40). Fuera de Docker no se define ninguna de estas variables
// y el backoffice funciona como siempre, con las URLs absolutas de .env.local.
//
// API_INTERNAL_URL: URL de la API dentro de la red de Docker (http://api:8000).
// Con ella, /backend/* se reenvía a la API (rewrite a una URL externa:
// node_modules/next/dist/docs/01-app/03-api-reference/05-config/01-next-config-js/rewrites.md),
// y el navegador usa NEXT_PUBLIC_API_URL=/backend sin conocer el nombre `api`.
// Solo de servidor: sin el prefijo NEXT_PUBLIC_ no llega al JavaScript del
// navegador. Se lee al arrancar `next dev`; con `next start`, los rewrites salen
// del routes-manifest.json que genera `next build`, así que en producción tiene
// que estar definida al construir.
const apiInternalUrl = process.env.API_INTERNAL_URL?.trim().replace(/\/+$/, "") ?? "";

// WATCHPACK_POLLING: la variable que ya lee el vigilante propio de Next
// (páginas nuevas, tsconfig, .env). Aquí se refleja en Turbopack con
// watchOptions.pollIntervalMs (tipado en next/dist/server/config-shared.d.ts;
// no aparece en la documentación de Next 16.3), para que un solo interruptor
// active el sondeo de los dos vigilantes. Pensado para el bind mount desde
// Windows de Docker (se verifica en la fase F4). Acepta los valores de
// Watchpack: un número de milisegundos o "true" (aquí, 1000 ms para Turbopack;
// Watchpack usa su propio intervalo).
const pollIntervalMs = pollingInterval(process.env.WATCHPACK_POLLING);

function pollingInterval(value: string | undefined): number | undefined {
  const normalized = value?.trim() ?? "";
  if (normalized === "" || normalized === "false") return undefined;
  if (/^\d+$/.test(normalized)) {
    const milliseconds = Number(normalized);
    return milliseconds > 0 ? milliseconds : undefined;
  }
  return 1000;
}

const nextConfig: NextConfig = {
  ...(pollIntervalMs === undefined ? {} : { watchOptions: { pollIntervalMs } }),
  async rewrites() {
    if (apiInternalUrl === "") return [];
    return [{ source: "/backend/:path*", destination: `${apiInternalUrl}/:path*` }];
  },
};

export default nextConfig;

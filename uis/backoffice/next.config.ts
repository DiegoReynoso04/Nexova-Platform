import type { NextConfig } from "next";

// Docker (#infra-40). Fuera de Docker no se define API_INTERNAL_URL y el
// backoffice funciona como siempre, con las URLs absolutas de .env.local.
//
// API_INTERNAL_URL: URL de la API dentro de la red de Docker (http://api:8000).
// Con ella, /backend/* se reenvía a la API (rewrite a una URL externa:
// node_modules/next/dist/docs/01-app/03-api-reference/05-config/01-next-config-js/rewrites.md),
// y el navegador usa NEXT_PUBLIC_API_URL=/backend sin conocer el nombre `api`.
// Solo de servidor: sin el prefijo NEXT_PUBLIC_ no llega al JavaScript del
// navegador. Se lee al arrancar `next dev`; con `next start`, los rewrites salen
// del routes-manifest.json que genera `next build`, así que en producción tiene
// que estar definida al construir.
//
// La recarga en Docker no se configura aquí: el contenedor arranca
// `next dev --webpack` (uis/start.sh) y Watchpack lee WATCHPACK_POLLING del
// entorno por su cuenta (docker-compose.yml).
const apiInternalUrl = process.env.API_INTERNAL_URL?.trim().replace(/\/+$/, "") ?? "";

const nextConfig: NextConfig = {
  async rewrites() {
    if (apiInternalUrl === "") return [];
    return [{ source: "/backend/:path*", destination: `${apiInternalUrl}/:path*` }];
  },
};

export default nextConfig;

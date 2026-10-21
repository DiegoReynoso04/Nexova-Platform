// Jest para la lógica TypeScript de autenticación (AUTH-088) y las utilidades del
// frontend (FE-019). Convive con los tests de `node --test` de tests/*.test.mjs:
// Jest solo recoge __tests__/**/*.test.ts.
// Plan, comandos y cobertura: services/api/TESTING.md.

/** @type {import('jest').Config} */
const config = {
  testEnvironment: 'node',
  roots: ['<rootDir>/__tests__'],
  testMatch: ['<rootDir>/__tests__/**/*.test.ts'],
  modulePathIgnorePatterns: ['<rootDir>/.next/'],
  moduleNameMapper: { '^@/(.*)$': '<rootDir>/$1' },
  transform: {
    // El tsconfig de Next usa `module: esnext` y `moduleResolution: bundler`; Jest necesita CommonJS.
    '^.+\\.tsx?$': ['ts-jest', { tsconfig: { module: 'commonjs', moduleResolution: 'node', jsx: 'react-jsx' } }],
  },
  collectCoverageFrom: [
    'lib/auth-token.ts',
    'lib/auth-routes.ts',
    'services/auth.service.ts',
    'services/normalizers.ts',
    'hooks/use-auth-session.ts',
    // Utilidades del frontend (__tests__/utils/).
    'lib/supplier-renewal.ts',
    'services/suppliers.service.ts',
    'services/incident-manager.service.ts',
    // Inventario (Hito 5): cantidad y validadores de los formularios.
    'services/inventory.service.ts',
    'lib/stock-level.ts',
    'lib/stock-check.ts',
    'lib/order-format.ts',
  ],
};

export default config;

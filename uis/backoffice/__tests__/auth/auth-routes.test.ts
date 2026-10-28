// lib/auth-routes.ts: qué hace el guard global en cada ruta según la sesión.
// Toda ruta es protegida salvo las públicas (/login, /register, /forgot-password)
// y las abiertas (/reset-password).

import { headerNavMode, isOpenPath, isPublicPath, routeAccess } from '@/lib/auth-routes';

describe('isPublicPath', () => {
  test.each(['/login', '/register', '/forgot-password', '/login/'])('%s is public', (path) => {
    expect(isPublicPath(path)).toBe(true);
  });

  test.each(['/', '/account/profile', '/reset-password', '/LOGIN', '/login/extra'])('%s is not public', (path) => {
    // Las rutas de Next distinguen mayúsculas: /LOGIN no es /login y queda protegida.
    expect(isPublicPath(path)).toBe(false);
  });
});

describe('isOpenPath', () => {
  test.each(['/reset-password', '/reset-password/'])('%s is open', (path) => {
    expect(isOpenPath(path)).toBe(true);
  });

  test.each(['/login', '/', '/reset-password/x'])('%s is not open', (path) => {
    expect(isOpenPath(path)).toBe(false);
  });
});

describe('routeAccess', () => {
  test.each(['anonymous', 'authenticated', 'checking'] as const)(
    '/reset-password renders with session %s (the email link must work even if another session is open)',
    (session) => {
      expect(routeAccess('/reset-password', session)).toBe('render');
    }
  );

  test('public pages render without a session and send a logged-in user home', () => {
    expect(routeAccess('/login', 'anonymous')).toBe('render');
    expect(routeAccess('/login/', 'authenticated')).toBe('redirect_home');
    expect(routeAccess('/forgot-password', 'authenticated')).toBe('redirect_home');
  });

  test('a protected page renders only with a validated session', () => {
    expect(routeAccess('/account/profile', 'authenticated')).toBe('render');
  });

  test.each([
    ['anonymous', 'redirect_login'],
    ['initializing', 'wait'],
    ['checking', 'wait'],
    ['error', 'error'],
    // Durante «Reintentar» se mantiene el aviso de error (con la carga en el botón), no la espera.
    ['retrying', 'error'],
  ] as const)('a protected page with session %s → %s', (session, expected) => {
    expect(routeAccess('/', session)).toBe(expected);
  });

  test.each(['/inventory', '/inventory/products', '/inventory/orders/inbound', '/inventory/orders/outbound', '/inventory/orders'])(
    'the inventory page %s redirects to the login without a session and renders with one',
    (path) => {
      expect(isPublicPath(path)).toBe(false);
      expect(isOpenPath(path)).toBe(false);
      expect(routeAccess(path, 'anonymous')).toBe('redirect_login');
      expect(routeAccess(path, 'authenticated')).toBe('render');
    }
  );

  test('an unknown or differently cased path is protected by default', () => {
    expect(routeAccess('/LOGIN', 'anonymous')).toBe('redirect_login');
    expect(routeAccess('/vista-nueva', 'anonymous')).toBe('redirect_login');
  });
});

// Cabecera (components/auth/account-nav.tsx): mientras se valida la sesión en
// una ruta protegida reserva el hueco de la navegación con sesión, para que la
// cabecera no crezca al llegar GET /auth/me y desplace la página (CLS, H1 de AUDIT.md).
describe('headerNavMode', () => {
  test.each(['/suppliers', '/incident-manager', '/inventory/products', '/', '/account/profile'])(
    'a protected page %s reserves the session navigation while initializing or checking',
    (path) => {
      expect(headerNavMode(path, 'initializing')).toBe('reserved');
      expect(headerNavMode(path, 'checking')).toBe('reserved');
    }
  );

  test.each(['/login', '/register', '/forgot-password', '/reset-password'])(
    'a public or open page %s reserves nothing while the session is unknown',
    (path) => {
      expect(headerNavMode(path, 'initializing')).toBe('none');
      expect(headerNavMode(path, 'checking')).toBe('none');
    }
  );

  test.each(['/suppliers', '/login', '/reset-password'])('a validated session shows the session navigation on %s', (path) => {
    expect(headerNavMode(path, 'authenticated')).toBe('session');
  });

  test.each(['/suppliers', '/login', '/reset-password'])('without a session, %s shows only login and register', (path) => {
    expect(headerNavMode(path, 'anonymous')).toBe('access');
  });

  test.each(['error', 'retrying'] as const)('a session that could not be validated (%s) shows no navigation', (session) => {
    // El guard muestra el aviso con «Reintentar» y «Cerrar sesión»; la cabecera, solo la marca.
    expect(headerNavMode('/suppliers', session)).toBe('none');
  });
});

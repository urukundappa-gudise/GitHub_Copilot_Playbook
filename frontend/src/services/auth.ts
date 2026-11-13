export type AuthUser = {
  oid: string;
  upn: string;
  email: string | null;
  name: string;
};

export type AuthBootstrap = {
  required: boolean;
  user: AuthUser | null;
};

export const signInUrl = '/api/v1/auth/login';

function isAuthUser(value: unknown): value is AuthUser {
  if (!value || typeof value !== 'object') return false;
  const user = value as Record<string, unknown>;
  return typeof user.oid === 'string'
    && typeof user.upn === 'string'
    && (typeof user.email === 'string' || user.email === null)
    && typeof user.name === 'string';
}

export async function getAuthSession(): Promise<AuthBootstrap> {
  const response = await fetch('/api/v1/auth/session', {
    credentials: 'include',
    cache: 'no-store',
    headers: { accept: 'application/json' },
  });
  const required = response.headers.get('x-authentication-required') !== 'false';
  if (response.status === 401) return { required, user: null };
  if (!response.ok) throw new Error('Authentication could not be verified.');

  const body: unknown = await response.json();
  if (!body || typeof body !== 'object') {
    throw new Error('Authentication could not be verified.');
  }
  const session = body as { authenticated?: unknown; user?: unknown };
  if (session.authenticated !== true || !isAuthUser(session.user)) {
    throw new Error('Authentication could not be verified.');
  }
  return { required, user: session.user };
}

import { NextAuthOptions, Session, User } from 'next-auth';
import { JWT } from 'next-auth/jwt';
import CredentialsProvider from 'next-auth/providers/credentials';

import { sessionTokenCookieName } from '@/lib/auth-cookie';

/**
 * NextAuth is a thin shell over FastAPI-owned auth.
 *
 * There is NO database adapter and NO Prisma here. `authorize()` posts to the
 * FastAPI `/api/v1/auth/login`, which verifies the password, mints a rolling
 * `user_sessions` row, and returns an opaque session token. We stash that token
 * (`apiToken`) inside the NextAuth httpOnly cookie; every server-side proxy to
 * FastAPI forwards it as `Authorization: Bearer <apiToken>`. FastAPI is the sole
 * source of truth for session validity — revocation and the sliding 30-day
 * window live there (see PLAN-staff-rolling-sessions-fastapi-auth.md).
 *
 * The cookie maxAge (30d) only has to outlive the FastAPI session; FastAPI
 * decides the real expiry, so an unchecked-remember-me 8h session is enforced
 * backend-side even though the cookie itself persists.
 */

function backendBaseUrl(): string {
  const url =
    process.env.FASTAPI_INTERNAL_URL?.replace(/\/$/, '') ||
    process.env.NEXT_PUBLIC_API_URL?.replace(/\/$/, '');
  if (url) return url;
  if (process.env.NODE_ENV === 'production') return 'http://backend:8000';
  throw new Error('Backend URL not configured. Set NEXT_PUBLIC_API_URL.');
}

const THIRTY_DAYS_SECONDS = 30 * 24 * 60 * 60;

const authOptions: NextAuthOptions = {
  providers: [
    CredentialsProvider({
      name: 'Credentials',
      credentials: {
        email: { label: 'Email', type: 'text' },
        password: { label: 'Password', type: 'password' },
        rememberMe: { label: 'Remember me', type: 'boolean' },
      },
      async authorize(credentials) {
        if (!credentials || !credentials.email || !credentials.password) {
          throw new Error(
            JSON.stringify({ code: 400, message: 'Please enter both email and password.' }),
          );
        }

        // NextAuth serializes credentials as strings — coerce the checkbox.
        // (Boolean true → "true", string "true"/"on" all count as checked.)
        const rememberMe = ['true', 'on', '1'].includes(
          String(credentials.rememberMe).toLowerCase(),
        );

        let res: Response;
        try {
          res = await fetch(`${backendBaseUrl()}/api/v1/auth/login`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
              email: credentials.email,
              password: credentials.password,
              remember_me: rememberMe,
            }),
          });
        } catch {
          throw new Error(
            JSON.stringify({ code: 503, message: 'Unable to reach the server. Please try again.' }),
          );
        }

        const data = await res.json().catch(() => ({}));
        if (!res.ok) {
          const message =
            (typeof data?.detail === 'string' && data.detail) ||
            data?.detail?.message ||
            'Invalid credentials.';
          throw new Error(JSON.stringify({ code: res.status, message }));
        }

        return {
          id: data.id,
          email: data.email,
          name: data.name || 'Anonymous',
          avatar: data.avatar ?? null,
          status: data.status,
          roleId: data.role_id || (data.role_ids?.[0] ?? null),
          roleIds: data.role_ids ?? (data.role_id ? [data.role_id] : []),
          roleName: data.role_name ?? null,
          // Opaque FastAPI session token — carried in the NextAuth cookie.
          apiToken: data.token,
        } as User;
      },
    }),
  ],
  session: {
    strategy: 'jwt',
    maxAge: THIRTY_DAYS_SECONDS,
  },
  callbacks: {
    async jwt({
      token,
      user,
      session,
      trigger,
    }: {
      token: JWT;
      user: User;
      session?: Session;
      trigger?: 'signIn' | 'signUp' | 'update';
    }) {
      if (trigger === 'update' && session?.user) {
        // Merge profile fields from update(); keep apiToken/exp/sub intact.
        const u = session.user as Record<string, unknown>;
        if (typeof u.avatar === 'string' || u.avatar === null) {
          token.avatar = u.avatar as string | null | undefined;
        }
        if (typeof u.name === 'string') token.name = u.name;
        if (typeof u.email === 'string') token.email = u.email;
        if (typeof u.id === 'string') token.id = u.id;
        if (Array.isArray(u.roles)) {
          const ids = (u.roles as { id: string }[]).map((r) => r.id);
          token.roleIds = ids;
          token.roleId = ids[0] ?? null;
        }
      } else if (user) {
        token.id = (user.id || token.sub) as string;
        token.email = user.email;
        token.name = user.name;
        token.avatar = user.avatar;
        token.status = user.status;
        token.roleId = user.roleId;
        token.roleIds = user.roleIds ?? (user.roleId ? [user.roleId] : []);
        token.roleName = user.roleName ?? null;
        token.apiToken = (user as { apiToken?: string }).apiToken;
      }

      return token;
    },
    async session({ session, token }: { session: Session; token: JWT }) {
      if (session.user) {
        session.user.id = token.id;
        session.user.email = token.email;
        session.user.name = token.name;
        session.user.avatar = token.avatar;
        session.user.status = token.status;
        session.user.roleId = token.roleId;
        session.user.roleIds = token.roleIds ?? (token.roleId ? [token.roleId] : []);
        session.user.roleName = token.roleName;
      }
      return session;
    },
  },
  pages: {
    signIn: '/signin',
  },
  // Per-instance cookie names so two local instances on different ports
  // (localhost:3000 vs localhost:3001) don't overwrite each other's session.
  // Browsers scope cookies by host only — port is ignored. Single source of
  // truth: sessionTokenCookieName() in lib/auth-cookie.ts.
  cookies: (() => {
    const suffix = process.env.NEXTAUTH_COOKIE_SUFFIX
      ? `.${process.env.NEXTAUTH_COOKIE_SUFFIX}`
      : '';
    if (!suffix) return undefined;
    const secure = (process.env.NEXTAUTH_URL ?? '').startsWith('https://');
    const prefix = secure ? '__Secure-' : '';
    return {
      sessionToken: {
        name: sessionTokenCookieName(),
        options: { httpOnly: true, sameSite: 'lax', path: '/', secure },
      },
      callbackUrl: {
        name: `${prefix}next-auth.callback-url${suffix}`,
        options: { sameSite: 'lax', path: '/', secure },
      },
      csrfToken: {
        name: `${secure ? '__Host-' : ''}next-auth.csrf-token${suffix}`,
        options: { httpOnly: true, sameSite: 'lax', path: '/', secure },
      },
    };
  })(),
  logger: {
    error(code, metadata) {
      if (code === 'CLIENT_FETCH_ERROR') {
        const msg =
          typeof metadata === 'object' &&
          metadata !== null &&
          'error' in metadata &&
          metadata.error instanceof Error
            ? metadata.error.message
            : metadata instanceof Error
              ? metadata.message
              : metadata;
        console.warn(
          '[next-auth][warn] Session fetch failed. If this persists, check that the app and NEXTAUTH_URL use the same origin.',
          msg,
        );
        return;
      }
      console.error(`[next-auth][error][${code}]`, metadata);
    },
    warn(code) {
      console.warn(`[next-auth][warn][${code}]`);
    },
    debug(code, metadata) {
      if (process.env.NODE_ENV === 'development') {
        console.debug(`[next-auth][debug][${code}]`, metadata);
      }
    },
  },
};

export default authOptions;

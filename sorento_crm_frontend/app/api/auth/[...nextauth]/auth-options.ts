import { PrismaAdapter } from '@next-auth/prisma-adapter';
import bcrypt from 'bcrypt';
import { NextAuthOptions, Session, User } from 'next-auth';
import { JWT } from 'next-auth/jwt';
import CredentialsProvider from 'next-auth/providers/credentials';
import GoogleProvider from 'next-auth/providers/google';
import prisma from '@/lib/prisma';
import { sessionTokenCookieName } from '@/lib/auth-cookie';

const authOptions: NextAuthOptions = {
  adapter: PrismaAdapter(prisma),
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
            JSON.stringify({
              code: 400,
              message: 'Please enter both email and password.',
            }),
          );
        }

        const user = await prisma.user.findUnique({
          where: { email: credentials.email },
        });

        if (!user) {
          throw new Error(
            JSON.stringify({
              code: 404,
              message: 'User not found. Please register first.',
            }),
          );
        }

        const isPasswordValid = await bcrypt.compare(
          credentials.password,
          user.password || '',
        );

        if (!isPasswordValid) {
          throw new Error(
            JSON.stringify({
              code: 401,
              message: 'Invalid credentials. Incorrect password.',
            }),
          );
        }

        if (user.status !== 'ACTIVE') {
          throw new Error(
            JSON.stringify({
              code: 403,
              message: 'Account not activated. Please verify your email.',
            }),
          );
        }

        // Update `lastSignInAt` field
        await prisma.user.update({
          where: { id: user.id },
          data: { lastSignInAt: new Date() },
        });

        const assignments = await (
          prisma as unknown as {
            userRoleAssignment: {
              findMany: (args: {
                where: { userId: string };
                select: { roleId: true };
              }) => Promise<{ roleId: string }[]>;
            };
          }
        ).userRoleAssignment.findMany({
          where: { userId: user.id },
          select: { roleId: true },
        });
        const roleIds = assignments.map((a) => a.roleId);

        return {
          id: user.id,
          status: user.status,
          email: user.email,
          name: user.name || 'Anonymous',
          roleId: roleIds[0] ?? null,
          roleIds,
          avatar: user.avatar,
        };
      },
    }),
    GoogleProvider({
      clientId: process.env.GOOGLE_CLIENT_ID!,
      clientSecret: process.env.GOOGLE_CLIENT_SECRET!,
      allowDangerousEmailAccountLinking: true,
      async profile(profile) {
        const existingUser = await prisma.user.findUnique({
          where: { email: profile.email },
        });

        if (existingUser) {
          // Update `lastSignInAt` field for existing users
          await prisma.user.update({
            where: { id: existingUser.id },
            data: {
              name: profile.name,
              avatar: profile.picture || null,
              lastSignInAt: new Date(),
            },
          });

          const assignments = await (
            prisma as unknown as {
              userRoleAssignment: {
                findMany: (args: {
                  where: { userId: string };
                  select: { roleId: true };
                }) => Promise<{ roleId: string }[]>;
              };
            }
          ).userRoleAssignment.findMany({
            where: { userId: existingUser.id },
            select: { roleId: true },
          });
          const roleIds = assignments.map((a) => a.roleId);
          const firstRoleId = roleIds[0] ?? null;

          return {
            id: existingUser.id,
            email: existingUser.email,
            name: existingUser.name || 'Anonymous',
            status: existingUser.status,
            roleId: firstRoleId,
            roleIds,
            roleName: null,
            avatar: existingUser.avatar,
          };
        }

        const defaultRole = await prisma.userRole.findFirst({
          where: { isDefault: true },
        });

        if (!defaultRole) {
          throw new Error(
            'Default role not found. Unable to create a new user.',
          );
        }

        // Create a new user and account (no roleId on User; use roleAssignments)
        const newUser = await prisma.user.create({
          data: {
            email: profile.email,
            name: profile.name,
            password: '', // No password for OAuth users
            avatar: profile.picture || null,
            emailVerifiedAt: new Date(),
            status: 'ACTIVE',
          } as Parameters<typeof prisma.user.create>[0]['data'],
        });

        const prismaWithAssignment = prisma as unknown as {
          userRoleAssignment: {
            create: (args: {
              data: { userId: string; roleId: string };
            }) => Promise<unknown>;
          };
        };
        await prismaWithAssignment.userRoleAssignment.create({
          data: { userId: newUser.id, roleId: defaultRole.id },
        });

        return {
          id: newUser.id,
          email: newUser.email,
          name: newUser.name || 'Anonymous',
          status: newUser.status,
          avatar: newUser.avatar,
          roleId: defaultRole.id,
          roleIds: [defaultRole.id],
          roleName: defaultRole.name,
        };
      },
    }),
  ],
  session: {
    strategy: 'jwt',
    maxAge: 24 * 60 * 60,
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
        // Merge profile fields from update(); do not replace the whole token (loses exp/iat/sub).
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
      } else {
        if (user) {
          const role = user.roleId
            ? await prisma.userRole.findUnique({
                where: { id: user.roleId },
              })
            : null;

          token.id = (user.id || token.sub) as string;
          token.email = user.email;
          token.name = user.name;
          token.avatar = user.avatar;
          token.status = user.status;
          token.roleId = user.roleId;
          token.roleIds = user.roleIds ?? (user.roleId ? [user.roleId] : []);
          token.roleName = role?.name;
        }
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
  // Browsers scope cookies by host only — port is ignored — so without a
  // suffix both instances share `next-auth.session-token` and clobber logins.
  // Set NEXTAUTH_COOKIE_SUFFIX=instance-b in the second instance's .env.local.
  cookies: (() => {
    const suffix = process.env.NEXTAUTH_COOKIE_SUFFIX
      ? `.${process.env.NEXTAUTH_COOKIE_SUFFIX}`
      : '';
    if (!suffix) return undefined;
    const secure = (process.env.NEXTAUTH_URL ?? '').startsWith('https://');
    const prefix = secure ? '__Secure-' : '';
    return {
      sessionToken: {
        // Shared with the getToken() callers (token route, api-proxy) so they read
        // the same cookie — see lib/auth-cookie.ts.
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
      // Downgrade CLIENT_FETCH_ERROR to warning – usually means session refetch failed
      // (e.g. server restart, network blip, or NEXTAUTH_URL/origin mismatch). Avoids noisy console.
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

import 'next-auth';
import 'next-auth/jwt';

declare module 'next-auth' {
  interface Session {
    user: {
      id: string;
      name: string;
      email: string;
      avatar?: string | null;
      roleId?: string | null;
      roleIds?: string[];
      roleName?: string | null;
      status: string;
    };
  }

  interface User {
    id: string;
    name: string;
    email: string;
    avatar?: string | null;
    roleId?: string | null;
    roleIds?: string[];
    roleName?: string | null;
    status: string;
    // Opaque FastAPI session token returned by /api/v1/auth/login.
    apiToken?: string;
  }
}

declare module 'next-auth/jwt' {
  interface JWT {
    id: string;
    name: string;
    email: string;
    avatar?: string | null;
    roleId?: string | null;
    roleIds?: string[];
    roleName?: string | null;
    status: string;
    // Opaque FastAPI session token forwarded as Bearer to /api/v1/*.
    apiToken?: string;
  }
}

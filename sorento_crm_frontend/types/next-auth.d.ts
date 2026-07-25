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
      // Multi-company isolation (PLAN §3.11 / §11). Active company is the JWT
      // claim source-of-truth; grants is the lightweight id list of switchable
      // companies. Both resolved from GET /companies/my-context at login.
      active_company_id?: string;
      company_grants?: string[];
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
    active_company_id?: string;
    company_grants?: string[];
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
    // Multi-company isolation: active company claim + switchable grant ids.
    active_company_id?: string;
    company_grants?: string[];
  }
}

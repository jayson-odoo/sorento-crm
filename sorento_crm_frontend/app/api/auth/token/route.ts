import { NextRequest, NextResponse } from 'next/server';
import { getToken } from 'next-auth/jwt';

import { sessionTokenCookieName } from '@/lib/auth-cookie';

/**
 * Returns the opaque FastAPI session token stored in the NextAuth cookie.
 *
 * FastAPI mints and owns the token (rolling user_sessions row); we no longer
 * re-sign a JWT here. The client sends this token as `Authorization: Bearer`
 * to /api/v1/*; FastAPI resolves + slides + revokes it.
 */
export async function GET(request: NextRequest) {
  try {
    const secret = process.env.NEXTAUTH_SECRET;
    if (!secret) {
      return NextResponse.json({ error: 'NEXTAUTH_SECRET not configured' }, { status: 500 });
    }

    const tokenPayload = await getToken({
      req: request,
      secret,
      raw: false,
      cookieName: sessionTokenCookieName(),
    });

    const apiToken = tokenPayload?.apiToken;
    if (!apiToken) {
      return NextResponse.json({ error: 'No valid session' }, { status: 401 });
    }

    return NextResponse.json({ token: apiToken });
  } catch (error) {
    console.error('Error getting token:', error);
    return NextResponse.json({ error: 'Failed to get token' }, { status: 500 });
  }
}

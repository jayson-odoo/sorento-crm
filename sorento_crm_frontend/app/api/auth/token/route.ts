import { NextRequest, NextResponse } from 'next/server';
import { getToken } from 'next-auth/jwt';
import jwt from 'jsonwebtoken';

/**
 * API route to get a signed JWT token for FastAPI.
 * NextAuth uses encrypted JWE tokens, so we decode and re-sign as a standard JWT.
 */
export async function GET(request: NextRequest) {
  try {
    const secret = process.env.NEXTAUTH_SECRET;
    
    if (!secret) {
      return NextResponse.json(
        { error: 'NEXTAUTH_SECRET not configured' },
        { status: 500 }
      );
    }

    // Get the decoded token payload from NextAuth (not raw encrypted token)
    const tokenPayload = await getToken({ 
      req: request, 
      secret,
      raw: false  // Get decoded payload, not encrypted token
    });

    if (!tokenPayload) {
      return NextResponse.json(
        { error: 'No valid token found' },
        { status: 401 }
      );
    }

    // Re-sign as a standard JWT (not encrypted) for FastAPI
    // FastAPI can decode this with the same secret
    const signedToken = jwt.sign(
      {
        sub: tokenPayload.id || tokenPayload.sub,
        id: tokenPayload.id,
        email: tokenPayload.email,
        name: tokenPayload.name,
        avatar: tokenPayload.avatar,
        status: tokenPayload.status,
        roleId: tokenPayload.roleId,
        roleName: tokenPayload.roleName,
      },
      secret,
      {
        algorithm: 'HS256',
        expiresIn: '24h', // Match NextAuth session duration
      }
    );

    return NextResponse.json({ token: signedToken });
  } catch (error) {
    console.error('Error getting token:', error);
    return NextResponse.json(
      { error: 'Failed to get token' },
      { status: 500 }
    );
  }
}

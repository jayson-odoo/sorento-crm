/**
 * Helper to proxy Next.js API routes to FastAPI backend.
 * This allows Next.js routes to forward requests to FastAPI without duplicating logic.
 */
import { NextRequest, NextResponse } from 'next/server';
import { getToken } from 'next-auth/jwt';
import jwt from 'jsonwebtoken';

/**
 * Get JWT token for FastAPI from NextAuth session
 */
async function getFastAPIToken(request: NextRequest): Promise<string | null> {
  const secret = process.env.NEXTAUTH_SECRET;
  if (!secret) return null;

  try {
    const tokenPayload = await getToken({ 
      req: request, 
      secret,
      raw: false
    });

    if (!tokenPayload) return null;

    // Re-sign as standard JWT for FastAPI
    return jwt.sign(
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
        expiresIn: '24h',
      }
    );
  } catch {
    return null;
  }
}

/**
 * Proxy a request to FastAPI backend
 */
export async function proxyToFastAPI(
  request: NextRequest,
  fastApiPath: string,
  options: {
    method?: string;
    body?: any;
    queryParams?: Record<string, string>;
    requireAuth?: boolean; // If false, allows requests without NextAuth token
  } = {}
): Promise<NextResponse> {
  // Use internal URL for server-side calls (from Next.js to FastAPI)
  // In production (Docker), use the service name 'backend' from docker-compose
  // In development, use localhost
  // FASTAPI_INTERNAL_URL should be set in production to http://backend:8000 (or the internal service URL)
  const apiUrl = process.env.NEXT_PUBLIC_API_URL || 
                 (process.env.NODE_ENV === 'production' 
                   ? 'http://backend:8000'  // Docker service name
                   : process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000');
  const method = options.method || request.method;
  
  // Build URL with query params
  const url = new URL(`${apiUrl}${fastApiPath}`);
  if (options.queryParams) {
    Object.entries(options.queryParams).forEach(([key, value]) => {
      if (value) url.searchParams.append(key, value);
    });
  }
  // Also include original query params
  request.nextUrl.searchParams.forEach((value, key) => {
    url.searchParams.append(key, value);
  });

  // Prepare headers - forward all original headers that might be needed
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
  };
  
  // Forward X-API-Key header if present (for API key authentication)
  const apiKey = request.headers.get('X-API-Key');
  if (apiKey) {
    headers['X-API-Key'] = apiKey;
  }
  
  // Forward Authorization header if present (for API keys or Bearer tokens)
  const authHeader = request.headers.get('Authorization');
  if (authHeader) {
    headers['Authorization'] = authHeader;
  } else {
    // Try to get NextAuth token if auth is required and no API key provided
    const requireAuth = options.requireAuth !== false; // Default to true
    if (requireAuth && !apiKey) {
      const token = await getFastAPIToken(request);
      if (token) {
        headers['Authorization'] = `Bearer ${token}`;
      }
    }
  }

  // Get body
  let body: string | undefined;
  if (options.body !== undefined) {
    body = JSON.stringify(options.body);
  } else if (method !== 'GET' && method !== 'HEAD') {
    try {
      body = await request.text();
    } catch {
      // No body
    }
  }

  try {
    const response = await fetch(url.toString(), {
      method,
      headers,
      body,
    });

    const data = await response.json().catch(() => ({}));
    
    return NextResponse.json(data, { status: response.status });
  } catch (error) {
    console.error('FastAPI proxy error:', error);
    return NextResponse.json(
      { message: 'Failed to connect to backend service' },
      { status: 500 }
    );
  }
}

import { NextRequest } from 'next/server';
import { proxyToFastAPI } from '@/lib/api-proxy';

/**
 * Proxy route for external access to complaints API.
 * 
 * This route allows external parties to call:
 * https://fe-sorento.foundryx.my/api/v1/complaints-management/complaints
 * 
 * Authentication options:
 * 1. X-API-Key header (for external parties)
 * 2. Authorization: Bearer <token> (for authenticated users)
 * 
 * The request will be proxied to the FastAPI backend running on port 8000.
 */
export async function GET(req: NextRequest) {
  return proxyToFastAPI(req, '/api/v1/complaints-management/complaints', {
    requireAuth: false, // Allow requests without NextAuth token (API key auth handled by backend)
  });
}

export async function POST(request: NextRequest) {
  const body = await request.json();
  return proxyToFastAPI(request, '/api/v1/complaints-management/complaints', {
    method: 'POST',
    body,
    requireAuth: false, // Allow requests without NextAuth token (API key auth handled by backend)
  });
}

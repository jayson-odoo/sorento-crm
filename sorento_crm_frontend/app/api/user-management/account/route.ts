import { NextRequest } from 'next/server';
import { proxyToFastAPI } from '@/lib/api-proxy';

export async function GET(req: NextRequest) {
  // Get current user from session - proxy to user endpoint with current user ID
  // Note: This might need to get user ID from session token
  return proxyToFastAPI(req, '/api/v1/user-management/users/me');
}

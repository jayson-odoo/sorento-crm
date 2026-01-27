import { NextRequest } from 'next/server';
import { proxyToFastAPI } from '@/lib/api-proxy';

export async function GET(req: NextRequest) {
  // This will get logs for current user - need to pass user_id from session
  // For now, proxy and let FastAPI extract user from token
  return proxyToFastAPI(req, '/api/v1/user-management/system-logs');
}

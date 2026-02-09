import { NextRequest } from 'next/server';
import { proxyToFastAPI } from '@/lib/api-proxy';

export async function GET(req: NextRequest) {
  return proxyToFastAPI(req, '/api/v1/resource-management/attachments');
}

export async function POST(request: NextRequest) {
  // Note: File uploads may need special handling
  // For now, proxy JSON data
  const body = await request.json();
  return proxyToFastAPI(request, '/api/v1/resource-management/attachments', {
    method: 'POST',
    body,
  });
}

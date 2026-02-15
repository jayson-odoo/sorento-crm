import { NextRequest } from 'next/server';
import { proxyToFastAPI } from '@/lib/api-proxy';

export async function GET(request: NextRequest) {
  return proxyToFastAPI(request, '/api/v1/resource-management/directories');
}

export async function POST(request: NextRequest) {
  const body = await request.json().catch(() => ({}));
  return proxyToFastAPI(request, '/api/v1/resource-management/directories', {
    method: 'POST',
    body,
  });
}

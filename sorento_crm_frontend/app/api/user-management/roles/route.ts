import { NextRequest } from 'next/server';
import { proxyToFastAPI } from '@/lib/api-proxy';

export async function GET(request: Request) {
  return proxyToFastAPI(request as NextRequest, '/api/v1/user-management/roles');
}

export async function POST(request: NextRequest) {
  const body = await request.json();
  return proxyToFastAPI(request, '/api/v1/user-management/roles', {
    method: 'POST',
    body,
  });
}

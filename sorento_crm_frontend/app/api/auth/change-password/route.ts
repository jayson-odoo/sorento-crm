import { NextRequest } from 'next/server';
import { proxyToFastAPI } from '@/lib/api-proxy';

export async function POST(request: NextRequest) {
  const body = await request.json();
  return proxyToFastAPI(request, '/api/v1/auth/change-password', {
    method: 'POST',
    body,
  });
}

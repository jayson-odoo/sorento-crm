import { NextRequest } from 'next/server';
import { proxyToFastAPI } from '@/lib/api-proxy';

export async function PUT(request: NextRequest) {
  const body = await request.json();
  return proxyToFastAPI(request, '/api/v1/user-management/settings/smtp', {
    method: 'PUT',
    body,
  });
}

import { NextRequest } from 'next/server';
import { proxyToFastAPI } from '@/lib/api-proxy';

export async function DELETE(request: NextRequest) {
  const body = await request.json();
  return proxyToFastAPI(request, '/api/v1/marketing/promotions/bulk', {
    method: 'DELETE',
    body,
  });
}

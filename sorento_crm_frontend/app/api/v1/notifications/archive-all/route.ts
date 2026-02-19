import { NextRequest } from 'next/server';
import { proxyToFastAPI } from '@/lib/api-proxy';

export async function POST(request: NextRequest) {
  return proxyToFastAPI(request, '/api/v1/notifications/archive-all', {
    method: 'POST',
    body: {},
  });
}

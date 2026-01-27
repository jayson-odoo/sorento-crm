import { NextRequest } from 'next/server';
import { proxyToFastAPI } from '@/lib/api-proxy';

export async function GET(req: NextRequest) {
  return proxyToFastAPI(req, '/api/v1/order-management/orders');
}

export async function POST(request: NextRequest) {
  const body = await request.json();
  return proxyToFastAPI(request, '/api/v1/order-management/orders', {
    method: 'POST',
    body,
  });
}

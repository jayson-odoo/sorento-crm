import { NextRequest } from 'next/server';
import { proxyToFastAPI } from '@/lib/api-proxy';

export async function GET(req: NextRequest) {
  return proxyToFastAPI(req, '/api/v1/procurement/product-suppliers');
}

export async function POST(request: NextRequest) {
  const body = await request.json();
  return proxyToFastAPI(request, '/api/v1/procurement/product-suppliers', {
    method: 'POST',
    body,
  });
}

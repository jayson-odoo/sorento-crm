import { NextRequest } from 'next/server';
import { proxyToFastAPI } from '@/lib/api-proxy';

export async function POST(request: NextRequest) {
  const body = await request.json();
  return proxyToFastAPI(request, '/api/v1/external/product-attachments/link-products', {
    method: 'POST',
    body,
    requireAuth: false,
  });
}

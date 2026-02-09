import { NextRequest } from 'next/server';
import { proxyToFastAPI } from '@/lib/api-proxy';

export async function PUT(request: NextRequest) {
  const body = await request.json();
  // Note: If FastAPI doesn't have this endpoint, it will return 404
  return proxyToFastAPI(request, '/api/v1/master-data/products/bulk', {
    method: 'PUT',
    body,
  });
}

export async function DELETE(request: NextRequest) {
  const body = await request.json();
  // Note: If FastAPI doesn't have this endpoint, it will return 404
  return proxyToFastAPI(request, '/api/v1/master-data/products/bulk', {
    method: 'DELETE',
    body,
  });
}

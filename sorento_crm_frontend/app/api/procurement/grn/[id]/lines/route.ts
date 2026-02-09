import { NextRequest } from 'next/server';
import { proxyToFastAPI } from '@/lib/api-proxy';

export async function POST(
  request: NextRequest,
  { params }: { params: Promise<{ id: string }> },
) {
  const { id } = await params;
  const body = await request.json();
  // Note: If FastAPI doesn't have this endpoint yet, it will return 404
  // The endpoint should be at /api/v1/procurement/grn/{id}/lines
  return proxyToFastAPI(request, `/api/v1/procurement/grn/${id}/lines`, {
    method: 'POST',
    body,
  });
}

import { NextRequest } from 'next/server';
import { proxyToFastAPI } from '@/lib/api-proxy';

export async function POST(
  request: NextRequest,
  { params }: { params: Promise<{ id: string }> },
) {
  const { id } = await params;
  const body = await request.json();
  // Note: If FastAPI doesn't have this endpoint, it will return 404
  return proxyToFastAPI(request, `/api/v1/forms-management/forms/${id}/sections`, {
    method: 'POST',
    body,
  });
}

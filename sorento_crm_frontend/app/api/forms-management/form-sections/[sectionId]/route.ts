import { NextRequest } from 'next/server';
import { proxyToFastAPI } from '@/lib/api-proxy';

export async function PUT(
  request: NextRequest,
  { params }: { params: Promise<{ sectionId: string }> },
) {
  const { sectionId } = await params;
  const body = await request.json();
  // Note: If FastAPI doesn't have this endpoint, it will return 404
  return proxyToFastAPI(request, `/api/v1/forms-management/form-sections/${sectionId}`, {
    method: 'PUT',
    body,
  });
}

export async function DELETE(
  request: NextRequest,
  { params }: { params: Promise<{ sectionId: string }> },
) {
  const { sectionId } = await params;
  // Note: If FastAPI doesn't have this endpoint, it will return 404
  return proxyToFastAPI(request, `/api/v1/forms-management/form-sections/${sectionId}`, {
    method: 'DELETE',
  });
}

import { NextRequest } from 'next/server';
import { proxyToFastAPI } from '@/lib/api-proxy';

export async function PUT(
  request: NextRequest,
  { params }: { params: Promise<{ id: string; contactId: string }> },
) {
  const { id, contactId } = await params;
  const body = await request.json();
  return proxyToFastAPI(request, `/api/v1/user-management/access-agents/${id}/contact-access/${contactId}`, {
    method: 'PUT',
    body,
  });
}

export async function DELETE(
  request: NextRequest,
  { params }: { params: Promise<{ id: string; contactId: string }> },
) {
  const { id, contactId } = await params;
  return proxyToFastAPI(request, `/api/v1/user-management/access-agents/${id}/contact-access/${contactId}`, {
    method: 'DELETE',
  });
}

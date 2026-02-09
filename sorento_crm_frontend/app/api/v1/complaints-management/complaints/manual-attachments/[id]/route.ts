import { NextRequest } from 'next/server';
import { proxyToFastAPI } from '@/lib/api-proxy';

export async function DELETE(
  request: NextRequest,
  { params }: { params: Promise<{ id: string }> },
) {
  const { id } = await params;
  return proxyToFastAPI(
    request,
    `/api/v1/complaints-management/complaints/manual-attachments/${id}`,
    {
      method: 'DELETE',
    },
  );
}

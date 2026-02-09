import { NextRequest } from 'next/server';
import { proxyToFastAPI } from '@/lib/api-proxy';

export async function POST(
  request: NextRequest,
  { params }: { params: Promise<{ id: string }> }
) {
  const { id } = await params;
  return proxyToFastAPI(request, `/api/v1/user-management/contacts/${id}/sync`, {
    method: 'POST',
  });
}

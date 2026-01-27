import { NextRequest } from 'next/server';
import { proxyToFastAPI } from '@/lib/api-proxy';

export async function GET(
  req: NextRequest,
  { params }: { params: Promise<{ spoId: string }> },
) {
  const { spoId } = await params;
  // Note: If FastAPI doesn't have this endpoint, it will return 404
  // Should be at /api/v1/procurement/grn/by-spo/{spoId}
  return proxyToFastAPI(req, `/api/v1/procurement/grn/by-spo/${spoId}`);
}

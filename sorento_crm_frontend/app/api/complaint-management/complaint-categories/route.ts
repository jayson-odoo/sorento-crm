import { NextRequest } from 'next/server';
import { proxyToFastAPI } from '@/lib/api-proxy';

export async function GET(req: NextRequest) {
  // Note: If FastAPI doesn't have this endpoint, it will return 404
  // Should be at /api/v1/complaints-management/complaint-categories
  return proxyToFastAPI(req, '/api/v1/complaints-management/complaint-categories');
}

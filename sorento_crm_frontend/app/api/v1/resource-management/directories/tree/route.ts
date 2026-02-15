import { NextRequest } from 'next/server';
import { proxyToFastAPI } from '@/lib/api-proxy';

export async function GET(request: NextRequest) {
  return proxyToFastAPI(request, '/api/v1/resource-management/directories/tree');
}

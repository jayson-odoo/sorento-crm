import { NextRequest } from 'next/server';
import { proxyToFastAPI } from '@/lib/api-proxy';

export async function POST(request: NextRequest) {
  // Note: File uploads need special handling
  // For now, proxy and let FastAPI handle it
  const formData = await request.formData();
  const body: Record<string, any> = {};
  formData.forEach((value, key) => {
    body[key] = value;
  });
  
  return proxyToFastAPI(request, '/api/v1/procurement/product-suppliers/bulk-upload', {
    method: 'POST',
    body,
  });
}

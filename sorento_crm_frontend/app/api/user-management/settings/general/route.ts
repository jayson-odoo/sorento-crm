import { NextRequest } from 'next/server';
import { proxyToFastAPI } from '@/lib/api-proxy';

export async function POST(request: NextRequest) {
  // Note: File uploads for logos need special handling
  // For now, this proxies JSON data only
  // File uploads should be handled separately or kept in Next.js
  const formData = await request.formData();
  const body: Record<string, any> = {};
  
  // Extract non-file fields
  formData.forEach((value, key) => {
    if (key !== 'logoFile') {
      body[key] = value;
    }
  });
  
  return proxyToFastAPI(request, '/api/v1/user-management/settings/general', {
    method: 'PUT',
    body,
  });
}

import { NextRequest, NextResponse } from 'next/server';
import { getServerSession } from 'next-auth/next';
import {
  getBackendBaseUrl,
  getFastAPITokenForRequest,
} from '@/lib/api-proxy';
import authOptions from '@/app/api/auth/[...nextauth]/auth-options';

/**
 * Profile updates (name + optional avatar) are proxied as multipart to FastAPI.
 * Avatar bytes are uploaded with backend S3Service (same AWS/CloudFront as attachments),
 * so Next.js does not need STORAGE_* / S3 credentials.
 */
export async function POST(request: NextRequest) {
  try {
    const session = await getServerSession(authOptions);

    if (!session) {
      return NextResponse.json(
        { message: 'Unauthorized request' },
        { status: 401 },
      );
    }

    const formData = await request.formData();
    const token = await getFastAPITokenForRequest(request);
    if (!token) {
      return NextResponse.json(
        { message: 'Unauthorized request' },
        { status: 401 },
      );
    }

    const apiUrl = getBackendBaseUrl();
    const response = await fetch(
      `${apiUrl}/api/v1/user-management/users/me/profile`,
      {
        method: 'PUT',
        headers: {
          Authorization: `Bearer ${token}`,
        },
        body: formData,
      },
    );

    const data = await response.json().catch(() => ({}));
    return NextResponse.json(data, { status: response.status });
  } catch (e) {
    console.error('Profile proxy error:', e);
    return NextResponse.json(
      { message: 'Oops! Something went wrong. Please try again in a moment.' },
      { status: 500 },
    );
  }
}

import { NextRequest, NextResponse } from 'next/server';
import { getServerSession } from 'next-auth/next';
import { getClientIP } from '@/lib/api';
import { deleteFromS3, uploadToS3 } from '@/lib/s3-upload';
import { proxyToFastAPI } from '@/lib/api-proxy';
import { AccountProfileSchema } from '@/app/(protected)/user-management/account/forms/account-profile-schema';
import authOptions from '@/app/api/auth/[...nextauth]/auth-options';

export async function POST(request: NextRequest) {
  try {
    const session = await getServerSession(authOptions);

    if (!session) {
      return NextResponse.json(
        { message: 'Unauthorized request' },
        { status: 401 },
      );
    }

    const clientIp = getClientIP(request);

    // Parse the form data
    const formData = await request.formData();

    // Extract form data
    const parsedData = {
      name: formData.get('name'),
      avatarFile: formData.get('avatarFile'),
      avatarAction: formData.get('avatarAction'),
    };

    // Validate the input using Zod schema
    const validationResult = AccountProfileSchema.safeParse(parsedData);
    if (!validationResult.success) {
      return NextResponse.json({ error: 'Invalid input.' }, { status: 400 });
    }

    const { name, avatarFile, avatarAction } = validationResult.data;

    // Handle avatar removal
    if (avatarAction === 'remove' && session.user?.avatar) {
      try {
        await deleteFromS3(session.user.avatar);
      } catch (error) {
        console.error('Failed to remove avatar from S3:', error);
      }
    }

    // Handle new avatar upload
    let avatarUrl = session.user?.avatar || null;
    if (
      avatarAction === 'save' &&
      avatarFile instanceof File &&
      avatarFile.size > 0
    ) {
      try {
        avatarUrl = await uploadToS3(avatarFile, 'avatars');
      } catch (error) {
        console.error('Failed to upload avatar to S3:', error);
        return NextResponse.json(
          { message: 'Failed to upload avatar.' },
          { status: 500 },
        );
      }
    }

    // Update user via FastAPI (file upload handled above)
    const body: Record<string, any> = { name };
    if (avatarAction === 'remove') {
      body.avatar = null;
    } else if (avatarAction === 'save' && avatarUrl) {
      body.avatar = avatarUrl;
    }

    return proxyToFastAPI(request, '/api/v1/user-management/users/me/profile', {
      method: 'PUT',
      body,
    });
  } catch {
    return NextResponse.json(
      { message: 'Oops! Something went wrong. Please try again in a moment.' },
      { status: 500 },
    );
  }
}

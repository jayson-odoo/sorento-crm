import { NextRequest, NextResponse } from 'next/server';
import { getServerSession } from 'next-auth/next';
import { prisma } from '@/lib/prisma';
import authOptions from '@/app/api/auth/[...nextauth]/auth-options';

export async function PUT(
  request: NextRequest,
  { params }: { params: Promise<{ sectionId: string }> },
) {
  try {
    const session = await getServerSession(authOptions);

    if (!session) {
      return NextResponse.json(
        { message: 'Unauthorized request' },
        { status: 401 },
      );
    }

    const { sectionId } = await params;
    const body = await request.json();
    const { field_orders } = body;

    // TODO: Implement reorder logic once Prisma models are added
    return NextResponse.json(
      { message: 'Form fields reorder endpoint - database tables need to be created first' },
      { status: 501 },
    );
  } catch (error) {
    console.error('Error reordering form fields:', error);
    return NextResponse.json(
      { message: 'Oops! Something went wrong. Please try again in a moment.' },
      { status: 500 },
    );
  }
}

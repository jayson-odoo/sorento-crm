import { NextResponse } from 'next/server';
import { getServerSession } from 'next-auth/next';
import { prisma } from '@/lib/prisma';
import authOptions from '@/app/api/auth/[...nextauth]/auth-options';

export async function GET(
  request: Request,
  { params }: { params: Promise<{ hash: string }> },
) {
  try {
    const session = await getServerSession(authOptions);

    if (!session) {
      return NextResponse.json(
        { message: 'Unauthorized request' },
        { status: 401 },
      );
    }

    const { hash } = await params;

    // TODO: Implement duplicate detection once Prisma models are added
    /*
    const duplicate = await prisma.attachment.findFirst({
      where: {
        file_hash: hash,
        is_deleted: false,
      },
    });

    return NextResponse.json(duplicate);
    */

    return NextResponse.json(null);
  } catch (error) {
    console.error('Error checking duplicate:', error);
    return NextResponse.json(
      { message: 'Oops! Something went wrong. Please try again in a moment.' },
      { status: 500 },
    );
  }
}

import { NextRequest, NextResponse } from 'next/server';
import { getServerSession } from 'next-auth/next';
import { prisma } from '@/lib/prisma';
import authOptions from '@/app/api/auth/[...nextauth]/auth-options';

export async function GET(req: NextRequest) {
  try {
    const session = await getServerSession(authOptions);

    if (!session) {
      return NextResponse.json(
        { message: 'Unauthorized request' },
        { status: 401 },
      );
    }

    const statuses = await prisma.complaintStatus.findMany({
      where: {
        isActive: true,
      },
      orderBy: {
        sequence: 'asc',
      },
    });

    // Transform to snake_case for frontend
    const transformedStatuses = statuses.map((status) => ({
      id: status.id,
      status_code: status.statusCode,
      status_name: status.statusName,
      description: status.description,
      sequence: status.sequence,
    }));

    return NextResponse.json({ data: transformedStatuses });
  } catch (error) {
    console.error('Error fetching complaint statuses:', error);
    return NextResponse.json(
      { message: 'Oops! Something went wrong. Please try again in a moment.' },
      { status: 500 },
    );
  }
}

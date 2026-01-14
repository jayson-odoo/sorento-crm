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

    const orderStatuses = await prisma.orderStatus.findMany({
      orderBy: {
        sequence: 'asc',
      },
      select: {
        id: true,
        statusCode: true,
        statusName: true,
      },
    });

    // Transform to snake_case for frontend
    const transformedOrderStatuses = orderStatuses.map((os) => ({
      id: os.id,
      status_code: os.statusCode,
      status_name: os.statusName,
    }));

    return NextResponse.json(transformedOrderStatuses);
  } catch (error) {
    console.error('Error fetching order statuses for select:', error);
    return NextResponse.json(
      { message: 'Oops! Something went wrong. Please try again in a moment.' },
      { status: 500 },
    );
  }
}

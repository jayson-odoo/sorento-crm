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

    const { searchParams } = new URL(req.url);
    const page = parseInt(searchParams.get('page') || '1', 10);
    const limit = parseInt(searchParams.get('limit') || '50', 10);

    const totalCount = await prisma.orderStatus.count();

    const orderStatuses = await prisma.orderStatus.findMany({
      skip: (page - 1) * limit,
      take: limit,
      include: {
        _count: {
          select: {
            orders: true,
          },
        },
      },
      orderBy: {
        sequence: 'asc',
      },
    });

    // Transform to snake_case for frontend
    const transformedOrderStatuses = orderStatuses.map((os) => ({
      id: os.id,
      status_code: os.statusCode,
      status_name: os.statusName,
      description: os.description,
      sequence: os.sequence,
      is_final_status: os.isFinalStatus,
      created_at: os.createdAt,
      orders_count: os._count?.orders || 0,
    }));

    return NextResponse.json({
      data: transformedOrderStatuses,
      pagination: {
        total: totalCount,
        page,
        limit,
      },
      empty: totalCount === 0,
    });
  } catch (error) {
    console.error('Error fetching order statuses:', error);
    return NextResponse.json(
      { message: 'Oops! Something went wrong. Please try again in a moment.' },
      { status: 500 },
    );
  }
}

export async function POST(request: NextRequest) {
  try {
    const session = await getServerSession(authOptions);

    if (!session) {
      return NextResponse.json(
        { message: 'Unauthorized request' },
        { status: 401 },
      );
    }

    const body = await request.json();

    const orderStatus = await prisma.orderStatus.create({
      data: {
        statusCode: body.status_code,
        statusName: body.status_name,
        description: body.description || null,
        sequence: body.sequence || 0,
        isFinalStatus: body.is_final_status || false,
      },
    });

    // Transform to snake_case for frontend
    const transformedOrderStatus = {
      id: orderStatus.id,
      status_code: orderStatus.statusCode,
      status_name: orderStatus.statusName,
      description: orderStatus.description,
      sequence: orderStatus.sequence,
      is_final_status: orderStatus.isFinalStatus,
      created_at: orderStatus.createdAt,
    };

    return NextResponse.json(transformedOrderStatus, { status: 201 });
  } catch (error) {
    console.error('Error creating order status:', error);
    
    // Handle unique constraint violation
    if (error instanceof Error && error.message.includes('Unique constraint')) {
      return NextResponse.json(
        { message: 'Status code already exists. Please use a different code.' },
        { status: 400 },
      );
    }

    return NextResponse.json(
      { message: 'Oops! Something went wrong. Please try again in a moment.' },
      { status: 500 },
    );
  }
}

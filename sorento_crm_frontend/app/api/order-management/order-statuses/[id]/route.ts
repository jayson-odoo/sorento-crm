import { NextRequest, NextResponse } from 'next/server';
import { getServerSession } from 'next-auth/next';
import { prisma } from '@/lib/prisma';
import authOptions from '@/app/api/auth/[...nextauth]/auth-options';

export async function GET(
  request: Request,
  { params }: { params: Promise<{ id: string }> },
) {
  try {
    const session = await getServerSession(authOptions);

    if (!session) {
      return NextResponse.json(
        { message: 'Unauthorized request' },
        { status: 401 },
      );
    }

    const { id } = await params;

    // Validate that id is a valid UUID format
    const uuidRegex = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
    if (!uuidRegex.test(id)) {
      return NextResponse.json(
        { message: 'Invalid order status ID format' },
        { status: 400 },
      );
    }

    const orderStatus = await prisma.orderStatus.findUnique({
      where: { id },
      include: {
        _count: {
          select: {
            orders: true,
          },
        },
      },
    });

    if (!orderStatus) {
      return NextResponse.json(
        { message: 'Order status not found' },
        { status: 404 },
      );
    }

    // Transform to snake_case for frontend
    const transformedOrderStatus = {
      id: orderStatus.id,
      status_code: orderStatus.statusCode,
      status_name: orderStatus.statusName,
      description: orderStatus.description,
      sequence: orderStatus.sequence,
      is_final_status: orderStatus.isFinalStatus,
      created_at: orderStatus.createdAt,
      orders_count: orderStatus._count?.orders || 0,
    };

    return NextResponse.json(transformedOrderStatus);
  } catch (error) {
    console.error('Error fetching order status:', error);
    return NextResponse.json(
      { message: 'Oops! Something went wrong. Please try again in a moment.' },
      { status: 500 },
    );
  }
}

export async function PUT(
  request: NextRequest,
  { params }: { params: Promise<{ id: string }> },
) {
  try {
    const session = await getServerSession(authOptions);

    if (!session) {
      return NextResponse.json(
        { message: 'Unauthorized request' },
        { status: 401 },
      );
    }

    const { id } = await params;

    // Validate that id is a valid UUID format
    const uuidRegex = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
    if (!uuidRegex.test(id)) {
      return NextResponse.json(
        { message: 'Invalid order status ID format' },
        { status: 400 },
      );
    }

    const body = await request.json();

    const orderStatus = await prisma.orderStatus.update({
      where: { id },
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

    return NextResponse.json(transformedOrderStatus);
  } catch (error) {
    console.error('Error updating order status:', error);
    
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

export async function DELETE(
  request: NextRequest,
  { params }: { params: Promise<{ id: string }> },
) {
  try {
    const session = await getServerSession(authOptions);

    if (!session) {
      return NextResponse.json(
        { message: 'Unauthorized request' },
        { status: 401 },
      );
    }

    const { id } = await params;

    // Validate that id is a valid UUID format
    const uuidRegex = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
    if (!uuidRegex.test(id)) {
      return NextResponse.json(
        { message: 'Invalid order status ID format' },
        { status: 400 },
      );
    }

    // Check if order status exists
    const orderStatus = await prisma.orderStatus.findUnique({
      where: { id },
    });

    if (!orderStatus) {
      return NextResponse.json(
        { message: 'Order status not found' },
        { status: 404 },
      );
    }

    // Permanently delete the order status
    await prisma.orderStatus.delete({
      where: { id },
    });

    return NextResponse.json({ message: 'Order status deleted successfully' });
  } catch (error) {
    console.error('Error deleting order status:', error);
    
    // Handle foreign key constraint errors
    if (error instanceof Error && error.message.includes('Foreign key constraint')) {
      return NextResponse.json(
        { message: 'Cannot delete order status. It is being used in orders.' },
        { status: 400 },
      );
    }

    return NextResponse.json(
      { message: 'Oops! Something went wrong. Please try again in a moment.' },
      { status: 500 },
    );
  }
}

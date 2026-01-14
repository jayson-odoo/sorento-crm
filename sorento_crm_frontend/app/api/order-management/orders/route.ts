import { NextRequest, NextResponse } from 'next/server';
import { getServerSession } from 'next-auth/next';
import { prisma } from '@/lib/prisma';
import authOptions from '@/app/api/auth/[...nextauth]/auth-options';

/**
 * Transform Prisma order to frontend expected format (snake_case)
 */
function transformOrder(order: any) {
  return {
    id: order.id,
    order_number: order.orderNumber,
    order_date: order.orderDate,
    promised_delivery_date: order.promisedDeliveryDate,
    actual_delivery_date: order.actualDeliveryDate,
    customer_id: order.customerId,
    order_status_id: order.orderStatusId,
    created_by: order.createdBy,
    updated_by: order.updatedBy,
    billing_address_id: order.billingAddressId,
    shipping_address_id: order.shippingAddressId,
    subtotal_amount: Number(order.subtotalAmount),
    discount_amount: Number(order.discountAmount),
    tax_amount: Number(order.taxAmount),
    total_amount: Number(order.totalAmount),
    remarks: order.remarks,
    created_at: order.createdAt,
    updated_at: order.updatedAt,
    deleted_at: order.deletedAt,
    synced_to_excel: order.syncedToExcel,
    last_synced_to_excel: order.lastSyncedToExcel,
    customer: order.customer ? {
      id: order.customer.id,
      customer_code: order.customer.customerCode,
      customer_name: order.customer.customerName,
    } : undefined,
    order_status: order.orderStatus ? {
      id: order.orderStatus.id,
      status_code: order.orderStatus.statusCode,
      status_name: order.orderStatus.statusName,
    } : undefined,
  };
}

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
    const query = searchParams.get('query') || '';
    const sortField = searchParams.get('sort') || 'created_at';
    const sortDirection = searchParams.get('dir') === 'desc' ? 'desc' : 'asc';
    const customerId = searchParams.get('customer_id') || null;
    const orderStatusId = searchParams.get('order_status_id') || null;

    // Build where clause with filters
    const whereClause: any = {
      deletedAt: null, // Only show non-deleted orders
      ...(customerId && customerId !== 'all' ? { customerId } : {}),
      ...(orderStatusId && orderStatusId !== 'all' ? { orderStatusId } : {}),
      ...(query
        ? {
            OR: [
              { orderNumber: { contains: query, mode: 'insensitive' } },
              { customer: { customerName: { contains: query, mode: 'insensitive' } } },
              { customer: { customerCode: { contains: query, mode: 'insensitive' } } },
            ],
          }
        : {}),
    };

    const totalCount = await prisma.order.count({ where: whereClause });

    // Map sort field
    const sortMap: Record<string, string> = {
      order_number: 'orderNumber',
      order_date: 'orderDate',
      total_amount: 'totalAmount',
      created_at: 'createdAt',
      updated_at: 'updatedAt',
    };
    const mappedSortField = sortMap[sortField] || 'createdAt';

    const orders = await prisma.order.findMany({
      where: whereClause,
      skip: (page - 1) * limit,
      take: limit,
      include: {
        customer: {
          select: {
            id: true,
            customerCode: true,
            customerName: true,
          },
        },
        orderStatus: {
          select: {
            id: true,
            statusCode: true,
            statusName: true,
          },
        },
      },
      orderBy: { [mappedSortField]: sortDirection },
    });

    // Transform to snake_case for frontend
    const transformedOrders = orders.map(transformOrder);

    return NextResponse.json({
      data: transformedOrders,
      pagination: {
        total: totalCount,
        page,
        limit,
      },
      empty: totalCount === 0,
    });
  } catch (error) {
    console.error('Error fetching orders:', error);
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

    // Calculate total if not provided
    const subtotal = Number(body.subtotal_amount) || 0;
    const discount = Number(body.discount_amount) || 0;
    const tax = Number(body.tax_amount) || 0;
    const total = subtotal - discount + tax;

    const order = await prisma.order.create({
      data: {
        orderNumber: body.order_number,
        orderDate: body.order_date ? new Date(body.order_date) : null,
        promisedDeliveryDate: body.promised_delivery_date ? new Date(body.promised_delivery_date) : null,
        actualDeliveryDate: body.actual_delivery_date ? new Date(body.actual_delivery_date) : null,
        customerId: body.customer_id || null,
        orderStatusId: body.order_status_id || null,
        billingAddressId: body.billing_address_id || null,
        shippingAddressId: body.shipping_address_id || null,
        subtotalAmount: subtotal,
        discountAmount: discount,
        taxAmount: tax,
        totalAmount: total,
        remarks: body.remarks || null,
        createdBy: session.user?.id || null,
      },
      include: {
        customer: {
          select: {
            id: true,
            customerCode: true,
            customerName: true,
          },
        },
        orderStatus: {
          select: {
            id: true,
            statusCode: true,
            statusName: true,
          },
        },
      },
    });

    // Transform to snake_case for frontend
    const transformedOrder = transformOrder(order);

    return NextResponse.json(transformedOrder, { status: 201 });
  } catch (error) {
    console.error('Error creating order:', error);
    
    // Handle unique constraint violation
    if (error instanceof Error && error.message.includes('Unique constraint')) {
      return NextResponse.json(
        { message: 'Order number already exists. Please use a different number.' },
        { status: 400 },
      );
    }

    return NextResponse.json(
      { message: 'Oops! Something went wrong. Please try again in a moment.' },
      { status: 500 },
    );
  }
}

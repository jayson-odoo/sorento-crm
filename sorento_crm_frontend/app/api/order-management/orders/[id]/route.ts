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
      email: order.customer.email,
      phone_number: order.customer.phoneNumber,
    } : undefined,
    order_status: order.orderStatus ? {
      id: order.orderStatus.id,
      status_code: order.orderStatus.statusCode,
      status_name: order.orderStatus.statusName,
      description: order.orderStatus.description,
    } : undefined,
  };
}

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
        { message: 'Invalid order ID format' },
        { status: 400 },
      );
    }

    const order = await prisma.order.findUnique({
      where: { id },
      include: {
        customer: {
          select: {
            id: true,
            customerCode: true,
            customerName: true,
            email: true,
            phoneNumber: true,
          },
        },
        orderStatus: {
          select: {
            id: true,
            statusCode: true,
            statusName: true,
            description: true,
          },
        },
      },
    });

    if (!order) {
      return NextResponse.json(
        { message: 'Order not found' },
        { status: 404 },
      );
    }

    // Transform to snake_case for frontend
    const transformedOrder = transformOrder(order);

    return NextResponse.json(transformedOrder);
  } catch (error) {
    console.error('Error fetching order:', error);
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
        { message: 'Invalid order ID format' },
        { status: 400 },
      );
    }

    const body = await request.json();

    // Calculate total if not provided
    const subtotal = typeof body.subtotal_amount === 'number' ? body.subtotal_amount : Number(body.subtotal_amount) || 0;
    const discount = typeof body.discount_amount === 'number' ? body.discount_amount : Number(body.discount_amount) || 0;
    const tax = typeof body.tax_amount === 'number' ? body.tax_amount : Number(body.tax_amount) || 0;
    const total = subtotal - discount + tax;

    const order = await prisma.order.update({
      where: { id },
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
        updatedBy: session.user?.id || null,
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

    return NextResponse.json(transformedOrder);
  } catch (error) {
    console.error('Error updating order:', error);
    
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
        { message: 'Invalid order ID format' },
        { status: 400 },
      );
    }

    // Check if order exists
    const order = await prisma.order.findUnique({
      where: { id },
    });

    if (!order) {
      return NextResponse.json(
        { message: 'Order not found' },
        { status: 404 },
      );
    }

    // Permanently delete the order
    await prisma.order.delete({
      where: { id },
    });

    return NextResponse.json({ message: 'Order deleted successfully' });
  } catch (error) {
    console.error('Error deleting order:', error);
    
    // Handle foreign key constraint errors
    if (error instanceof Error && error.message.includes('Foreign key constraint')) {
      return NextResponse.json(
        { message: 'Cannot delete order. It is being used in other records.' },
        { status: 400 },
      );
    }

    return NextResponse.json(
      { message: 'Oops! Something went wrong. Please try again in a moment.' },
      { status: 500 },
    );
  }
}

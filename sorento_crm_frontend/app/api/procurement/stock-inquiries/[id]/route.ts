import { NextRequest, NextResponse } from 'next/server';
import { getServerSession } from 'next-auth/next';
import { prisma } from '@/lib/prisma';
import authOptions from '@/app/api/auth/[...nextauth]/auth-options';

/**
 * Transform Prisma stock inquiry to frontend expected format (snake_case)
 */
function transformStockInquiry(inquiry: any) {
  return {
    id: inquiry.id,
    salesperson: inquiry.salesperson,
    product_code: inquiry.productCode,
    item_description: inquiry.itemDescription,
    project_customer: inquiry.projectCustomer,
    project_name: inquiry.projectName,
    quantity: inquiry.quantity ? Number(inquiry.quantity) : null,
    delivery_date: inquiry.deliveryDate,
    brand: inquiry.brand,
    additional_remark: inquiry.additionalRemark,
    purchasing_response: inquiry.purchasingResponse,
    created_at: inquiry.createdAt,
    updated_at: inquiry.updatedAt,
  };
}

export async function GET(
  req: NextRequest,
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

    // Skip validation for special routes
    if (id === 'new' || id === 'edit') {
      return NextResponse.json(
        { message: 'Invalid stock inquiry ID' },
        { status: 404 },
      );
    }

    // Validate UUID format
    const uuidRegex =
      /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
    if (!uuidRegex.test(id)) {
      return NextResponse.json(
        { message: 'Invalid stock inquiry ID format' },
        { status: 400 },
      );
    }

    const inquiry = await prisma.stockInquiry.findUnique({
      where: { id },
    });

    if (!inquiry) {
      return NextResponse.json(
        { message: 'Stock inquiry not found' },
        { status: 404 },
      );
    }

    // Transform to snake_case for frontend
    const transformedInquiry = transformStockInquiry(inquiry);

    return NextResponse.json(transformedInquiry);
  } catch (error) {
    console.error('Error fetching stock inquiry:', error);
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
    const body = await request.json();

    const inquiry = await prisma.stockInquiry.update({
      where: { id },
      data: {
        salesperson: body.salesperson !== undefined ? body.salesperson : undefined,
        productCode: body.product_code !== undefined ? body.product_code : undefined,
        itemDescription: body.item_description !== undefined ? body.item_description : undefined,
        projectCustomer: body.project_customer !== undefined ? body.project_customer : undefined,
        projectName: body.project_name !== undefined ? body.project_name : undefined,
        quantity: body.quantity !== undefined ? (body.quantity ? parseFloat(body.quantity) : null) : undefined,
        deliveryDate: body.delivery_date !== undefined
          ? (body.delivery_date ? new Date(body.delivery_date) : null)
          : undefined,
        brand: body.brand !== undefined ? body.brand : undefined,
        additionalRemark: body.additional_remark !== undefined ? body.additional_remark : undefined,
        purchasingResponse: body.purchasing_response !== undefined ? body.purchasing_response : undefined,
      },
    });

    // Transform to snake_case for frontend
    const transformedInquiry = transformStockInquiry(inquiry);

    return NextResponse.json(transformedInquiry);
  } catch (error) {
    console.error('Error updating stock inquiry:', error);

    if (
      error instanceof Error &&
      error.message.includes('Record to update not found')
    ) {
      return NextResponse.json(
        { message: 'Stock inquiry not found' },
        { status: 404 },
      );
    }

    return NextResponse.json(
      { message: 'Oops! Something went wrong. Please try again in a moment.' },
      { status: 500 },
    );
  }
}

export async function DELETE(
  req: NextRequest,
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

    await prisma.stockInquiry.delete({
      where: { id },
    });

    return NextResponse.json({ message: 'Stock inquiry deleted successfully' });
  } catch (error) {
    console.error('Error deleting stock inquiry:', error);

    if (
      error instanceof Error &&
      error.message.includes('Record to delete does not exist')
    ) {
      return NextResponse.json(
        { message: 'Stock inquiry not found' },
        { status: 404 },
      );
    }

    return NextResponse.json(
      { message: 'Oops! Something went wrong. Please try again in a moment.' },
      { status: 500 },
    );
  }
}

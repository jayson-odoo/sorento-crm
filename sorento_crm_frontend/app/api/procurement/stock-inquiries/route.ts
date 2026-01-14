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

    // Build where clause with filters
    const whereClause: any = {
      ...(query
        ? {
            OR: [
              { salesperson: { contains: query, mode: 'insensitive' } },
              { productCode: { contains: query, mode: 'insensitive' } },
              { itemDescription: { contains: query, mode: 'insensitive' } },
              { projectCustomer: { contains: query, mode: 'insensitive' } },
              { projectName: { contains: query, mode: 'insensitive' } },
              { brand: { contains: query, mode: 'insensitive' } },
            ],
          }
        : {}),
    };

    const totalCount = await prisma.stockInquiry.count({ where: whereClause });

    // Map sort field
    const sortMap: Record<string, string> = {
      created_at: 'createdAt',
      updated_at: 'updatedAt',
      delivery_date: 'deliveryDate',
      product_code: 'productCode',
      project_customer: 'projectCustomer',
      project_name: 'projectName',
    };
    const mappedSortField = sortMap[sortField] || 'createdAt';

    const inquiries = await prisma.stockInquiry.findMany({
      where: whereClause,
      skip: (page - 1) * limit,
      take: limit,
      orderBy: { [mappedSortField]: sortDirection },
    });

    // Transform to snake_case for frontend
    const transformedInquiries = inquiries.map(transformStockInquiry);

    return NextResponse.json({
      data: transformedInquiries,
      pagination: {
        total: totalCount,
        page,
        limit,
      },
      empty: totalCount === 0,
    });
  } catch (error) {
    console.error('Error fetching stock inquiries:', error);
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

    const inquiry = await prisma.stockInquiry.create({
      data: {
        salesperson: body.salesperson || null,
        productCode: body.product_code || null,
        itemDescription: body.item_description || null,
        projectCustomer: body.project_customer || null,
        projectName: body.project_name || null,
        quantity: body.quantity ? parseFloat(body.quantity) : null,
        deliveryDate: body.delivery_date
          ? new Date(body.delivery_date)
          : null,
        brand: body.brand || null,
        additionalRemark: body.additional_remark || null,
        purchasingResponse: body.purchasing_response || null,
      },
    });

    // Transform to snake_case for frontend
    const transformedInquiry = transformStockInquiry(inquiry);

    return NextResponse.json(transformedInquiry, { status: 201 });
  } catch (error) {
    console.error('Error creating stock inquiry:', error);
    return NextResponse.json(
      { message: 'Oops! Something went wrong. Please try again in a moment.' },
      { status: 500 },
    );
  }
}

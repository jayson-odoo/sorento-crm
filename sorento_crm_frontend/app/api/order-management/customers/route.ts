import { NextRequest, NextResponse } from 'next/server';
import { getServerSession } from 'next-auth/next';
import { prisma } from '@/lib/prisma';
import authOptions from '@/app/api/auth/[...nextauth]/auth-options';

/**
 * Transform Prisma customer to frontend expected format (snake_case)
 */
function transformCustomer(customer: any) {
  return {
    id: customer.id,
    customer_code: customer.customerCode,
    customer_name: customer.customerName,
    email: customer.email,
    phone_number: customer.phoneNumber,
    is_active: customer.isActive,
    created_at: customer.createdAt,
    updated_at: customer.updatedAt,
    created_by: customer.createdBy,
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
    const status = searchParams.get('status') || 'all';

    // Build where clause with filters
    const whereClause: any = {
      ...(status && status !== 'all'
        ? { isActive: status === 'active' }
        : {}),
      ...(query
        ? {
            OR: [
              { customerCode: { contains: query, mode: 'insensitive' } },
              { customerName: { contains: query, mode: 'insensitive' } },
              { email: { contains: query, mode: 'insensitive' } },
            ],
          }
        : {}),
    };

    const totalCount = await prisma.customer.count({ where: whereClause });

    // Map sort field
    const sortMap: Record<string, string> = {
      customer_code: 'customerCode',
      customer_name: 'customerName',
      created_at: 'createdAt',
    };
    const mappedSortField = sortMap[sortField] || 'createdAt';

    const customers = await prisma.customer.findMany({
      where: whereClause,
      skip: (page - 1) * limit,
      take: limit,
      include: {
        _count: {
          select: {
            orders: true,
          },
        },
      },
      orderBy: { [mappedSortField]: sortDirection },
    });

    // Transform to snake_case for frontend
    const transformedCustomers = customers.map((customer: {
      id: string;
      customerCode: string;
      customerName: string;
      email: string | null;
      phoneNumber: string | null;
      isActive: boolean;
      createdAt: Date;
      updatedAt: Date | null;
      createdBy: string | null;
      _count?: { orders: number };
    }) => ({
      ...transformCustomer(customer),
      orders_count: customer._count?.orders || 0,
    }));

    return NextResponse.json({
      data: transformedCustomers,
      pagination: {
        total: totalCount,
        page,
        limit,
      },
      empty: totalCount === 0,
    });
  } catch (error) {
    console.error('Error fetching customers:', error);
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

    const customer = await prisma.customer.create({
      data: {
        customerCode: body.customer_code,
        customerName: body.customer_name,
        email: body.email || null,
        phoneNumber: body.phone_number || null,
        isActive: body.is_active !== false,
        createdBy: session.user?.id || null,
      },
    });

    // Transform to snake_case for frontend
    const transformedCustomer = transformCustomer(customer);

    return NextResponse.json(transformedCustomer, { status: 201 });
  } catch (error) {
    console.error('Error creating customer:', error);
    
    // Handle unique constraint violation
    if (error instanceof Error && error.message.includes('Unique constraint')) {
      return NextResponse.json(
        { message: 'Customer code already exists. Please use a different code.' },
        { status: 400 },
      );
    }

    return NextResponse.json(
      { message: 'Oops! Something went wrong. Please try again in a moment.' },
      { status: 500 },
    );
  }
}

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
    const query = searchParams.get('query') || '';
    const sortField = searchParams.get('sort') || 'created_at';
    const sortDirection = searchParams.get('dir') === 'desc' ? 'desc' : 'asc';

    const whereClause: any = {
      ...(query ? {
        OR: [
          { supplierCode: { contains: query, mode: 'insensitive' } },
          { supplierName: { contains: query, mode: 'insensitive' } },
        ],
      } : {}),
    };

    const sortMap: Record<string, any> = {
      'created_at': 'createdAt',
      'supplier_code': 'supplierCode',
      'supplier_name': 'supplierName',
    };
    const mappedSortField = sortMap[sortField] || 'createdAt';

    const totalCount = await prisma.supplier.count({ where: whereClause });

    const suppliers = await prisma.supplier.findMany({
      where: whereClause,
      skip: (page - 1) * limit,
      take: limit,
      orderBy: { [mappedSortField]: sortDirection },
    });

    // Transform to snake_case for frontend
    const transformedSuppliers = suppliers.map((supplier) => ({
      id: supplier.id,
      supplier_code: supplier.supplierCode,
      supplier_name: supplier.supplierName,
      contact_name: supplier.contactName,
      email: supplier.email,
      phone_number: supplier.phoneNumber,
      website: supplier.website,
      address_line1: supplier.addressLine1,
      address_line2: supplier.addressLine2,
      city: supplier.city,
      state: supplier.state,
      postal_code: supplier.postalCode,
      country: supplier.country,
      payment_terms_days: supplier.paymentTermsDays,
      is_active: supplier.isActive,
      created_at: supplier.createdAt,
      updated_at: supplier.updatedAt,
    }));

    return NextResponse.json({
      data: transformedSuppliers,
      pagination: {
        total: totalCount,
        page,
        limit,
      },
      empty: totalCount === 0,
    });
  } catch (error) {
    console.error('Error fetching suppliers:', error);
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

    const supplier = await prisma.supplier.create({
      data: {
        supplierCode: body.supplier_code,
        supplierName: body.supplier_name,
        contactName: body.contact_name || null,
        email: body.email || null,
        phoneNumber: body.phone_number || null,
        website: body.website || null,
        addressLine1: body.address_line1 || null,
        addressLine2: body.address_line2 || null,
        city: body.city || null,
        state: body.state || null,
        postalCode: body.postal_code || null,
        country: body.country || null,
        paymentTermsDays: body.payment_terms_days || 30,
        isActive: body.is_active !== false,
        createdBy: session.user?.id || null,
      },
    });

    return NextResponse.json(supplier, { status: 201 });
  } catch (error) {
    console.error('Error creating supplier:', error);
    return NextResponse.json(
      { message: 'Oops! Something went wrong. Please try again in a moment.' },
      { status: 500 },
    );
  }
}

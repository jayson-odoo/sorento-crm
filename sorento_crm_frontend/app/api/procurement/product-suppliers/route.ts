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

    const totalCount = await prisma.productSupplier.count();

    const productSuppliers = await prisma.productSupplier.findMany({
      skip: (page - 1) * limit,
      take: limit,
      include: {
        product: {
          select: {
            id: true,
            productCode: true,
            productName: true,
          },
        },
        supplier: {
          select: {
            id: true,
            supplierCode: true,
            supplierName: true,
          },
        },
      },
    });

    // Transform to snake_case for frontend
    const transformedProductSuppliers = productSuppliers.map((ps) => ({
      id: ps.id,
      product_id: ps.productId,
      supplier_id: ps.supplierId,
      created_at: ps.createdAt,
      product: ps.product ? {
        id: ps.product.id,
        product_code: ps.product.productCode,
        product_name: ps.product.productName,
      } : undefined,
      supplier: ps.supplier ? {
        id: ps.supplier.id,
        supplier_code: ps.supplier.supplierCode,
        supplier_name: ps.supplier.supplierName,
      } : undefined,
    }));

    return NextResponse.json({
      data: transformedProductSuppliers,
      pagination: {
        total: totalCount,
        page,
        limit,
      },
      empty: totalCount === 0,
    });
  } catch (error) {
    console.error('Error fetching product suppliers:', error);
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
    const leadTimeDays = body.standard_lead_time_days || body.lead_time_days || 0;

    // Use raw query since Prisma schema doesn't include standard_lead_time_days yet
    const result = await prisma.$queryRaw<Array<{ id: string }>>`
      INSERT INTO product_suppliers (id, product_id, supplier_id, standard_lead_time_days, created_at)
      VALUES (gen_random_uuid(), ${body.product_id}::uuid, ${body.supplier_id}::uuid, ${leadTimeDays}, NOW())
      RETURNING id
    `;

    if (!result || result.length === 0) {
      return NextResponse.json(
        { message: 'Failed to create product supplier' },
        { status: 500 },
      );
    }

    const createdId = result[0].id;

    // Fetch the created record with relations
    const productSupplier = await prisma.productSupplier.findUnique({
      where: { id: createdId },
      include: {
        product: {
          select: {
            id: true,
            productCode: true,
            productName: true,
          },
        },
        supplier: {
          select: {
            id: true,
            supplierCode: true,
            supplierName: true,
          },
        },
      },
    });

    if (!productSupplier) {
      return NextResponse.json(
        { message: 'Failed to fetch created product supplier' },
        { status: 500 },
      );
    }

    // Fetch standard_lead_time_days using raw query
    const leadTimeResult = await prisma.$queryRaw<Array<{ standard_lead_time_days: number | null }>>`
      SELECT standard_lead_time_days
      FROM product_suppliers
      WHERE id = ${createdId}::uuid
    `;
    const leadTimeDaysValue = leadTimeResult[0]?.standard_lead_time_days ?? null;

    // Transform to snake_case for frontend
    const transformedProductSupplier = {
      id: productSupplier.id,
      product_id: productSupplier.productId,
      supplier_id: productSupplier.supplierId,
      standard_lead_time_days: leadTimeDaysValue,
      lead_time_days: leadTimeDaysValue, // Alias for compatibility
      created_at: productSupplier.createdAt,
      product: productSupplier.product ? {
        id: productSupplier.product.id,
        product_code: productSupplier.product.productCode,
        product_name: productSupplier.product.productName,
      } : undefined,
      supplier: productSupplier.supplier ? {
        id: productSupplier.supplier.id,
        supplier_code: productSupplier.supplier.supplierCode,
        supplier_name: productSupplier.supplier.supplierName,
      } : undefined,
    };

    return NextResponse.json(transformedProductSupplier, { status: 201 });
  } catch (error) {
    console.error('Error creating product supplier:', error);
    return NextResponse.json(
      { message: 'Oops! Something went wrong. Please try again in a moment.' },
      { status: 500 },
    );
  }
}

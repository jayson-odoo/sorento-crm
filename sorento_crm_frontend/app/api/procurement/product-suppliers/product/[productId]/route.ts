import { NextRequest, NextResponse } from 'next/server';
import { getServerSession } from 'next-auth/next';
import { prisma } from '@/lib/prisma';
import authOptions from '@/app/api/auth/[...nextauth]/auth-options';

export async function GET(
  request: Request,
  { params }: { params: Promise<{ productId: string }> },
) {
  try {
    const session = await getServerSession(authOptions);

    if (!session) {
      return NextResponse.json(
        { message: 'Unauthorized request' },
        { status: 401 },
      );
    }

    const { productId } = await params;

    // Validate that productId is a valid UUID format
    const uuidRegex = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
    if (!uuidRegex.test(productId)) {
      return NextResponse.json(
        { message: 'Invalid product ID format' },
        { status: 400 },
      );
    }

    // Use raw query to include standard_lead_time_days field
    const productSuppliersRaw = await prisma.$queryRaw<Array<{
      id: string;
      product_id: string;
      supplier_id: string;
      standard_lead_time_days: number | null;
      created_at: Date;
    }>>`
      SELECT 
        ps.id,
        ps.product_id,
        ps.supplier_id,
        ps.standard_lead_time_days,
        ps.created_at
      FROM product_suppliers ps
      WHERE ps.product_id = ${productId}::uuid
      ORDER BY ps.created_at DESC
    `;

    // Fetch supplier details for each product supplier
    const transformedProductSuppliers = await Promise.all(
      productSuppliersRaw.map(async (ps) => {
        const supplier = await prisma.supplier.findUnique({
          where: { id: ps.supplier_id },
          select: {
            id: true,
            supplierCode: true,
            supplierName: true,
          },
        });

        return {
          id: ps.id,
          product_id: ps.product_id,
          supplier_id: ps.supplier_id,
          standard_lead_time_days: ps.standard_lead_time_days,
          lead_time_days: ps.standard_lead_time_days, // Alias for compatibility
          created_at: ps.created_at,
          supplier: supplier ? {
            id: supplier.id,
            supplier_code: supplier.supplierCode,
            supplier_name: supplier.supplierName,
          } : undefined,
        };
      })
    );

    return NextResponse.json(transformedProductSuppliers);
  } catch (error) {
    console.error('Error fetching product suppliers:', error);
    return NextResponse.json(
      { message: 'Oops! Something went wrong. Please try again in a moment.' },
      { status: 500 },
    );
  }
}

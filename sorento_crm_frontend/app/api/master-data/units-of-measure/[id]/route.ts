import { NextRequest, NextResponse } from 'next/server';
import { getServerSession } from 'next-auth/next';
import { prisma } from '@/lib/prisma';
import authOptions from '@/app/api/auth/[...nextauth]/auth-options';

/**
 * Transform Prisma UOM to frontend expected format (snake_case)
 */
function transformUOM(uom: any) {
  return {
    id: uom.id,
    uom_code: uom.uomCode,
    uom_name: uom.uomName,
    base_uom_id: uom.baseUomId,
    conversion_factor: uom.conversionFactor ? Number(uom.conversionFactor) : null,
    description: uom.description,
    created_at: uom.createdAt,
    updated_at: uom.updatedAt,
    base_uom: uom.baseUom ? {
      id: uom.baseUom.id,
      uom_code: uom.baseUom.uomCode,
      uom_name: uom.baseUom.uomName,
    } : undefined,
  };
}

/**
 * GET /api/master-data/units-of-measure/:id
 * 
 * Fetch a single UOM by ID
 */
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
        { message: 'Invalid UOM ID format' },
        { status: 400 },
      );
    }

    const uom = await prisma.unitOfMeasure.findUnique({
      where: { id },
      include: {
        baseUom: true,
      },
    });

    if (!uom) {
      return NextResponse.json(
        { message: 'UOM not found' },
        { status: 404 },
      );
    }

    return NextResponse.json(transformUOM(uom));
  } catch (error) {
    console.error('Error fetching UOM:', error);
    return NextResponse.json(
      { message: 'Oops! Something went wrong. Please try again in a moment.' },
      { status: 500 },
    );
  }
}

/**
 * PUT /api/master-data/units-of-measure/:id
 * 
 * Update a UOM
 */
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
        { message: 'Invalid UOM ID format' },
        { status: 400 },
      );
    }

    const body = await request.json();

    const uom = await prisma.unitOfMeasure.update({
      where: { id },
      data: {
        uomCode: body.uom_code,
        uomName: body.uom_name,
        baseUomId: body.base_uom_id || null,
        conversionFactor: body.conversion_factor || null,
        description: body.description || null,
      },
      include: {
        baseUom: true,
      },
    });

    return NextResponse.json(transformUOM(uom));
  } catch (error) {
    console.error('Error updating UOM:', error);
    return NextResponse.json(
      { message: 'Oops! Something went wrong. Please try again in a moment.' },
      { status: 500 },
    );
  }
}

/**
 * DELETE /api/master-data/units-of-measure/:id
 * 
 * Delete a UOM (hard delete - UOMs don't have isActive field)
 */
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
        { message: 'Invalid UOM ID format' },
        { status: 400 },
      );
    }

    // Check if UOM is used by any products
    const productCount = await prisma.product.count({
      where: { baseUomId: id },
    });

    if (productCount > 0) {
      return NextResponse.json(
        { message: `Cannot delete UOM: it is used by ${productCount} product(s)` },
        { status: 400 },
      );
    }

    await prisma.unitOfMeasure.delete({
      where: { id },
    });

    return NextResponse.json({ message: 'UOM deleted successfully' });
  } catch (error) {
    console.error('Error deleting UOM:', error);
    return NextResponse.json(
      { message: 'Oops! Something went wrong. Please try again in a moment.' },
      { status: 500 },
    );
  }
}

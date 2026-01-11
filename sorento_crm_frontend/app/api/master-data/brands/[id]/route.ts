import { NextRequest, NextResponse } from 'next/server';
import { getServerSession } from 'next-auth/next';
import { prisma } from '@/lib/prisma';
import authOptions from '@/app/api/auth/[...nextauth]/auth-options';

/**
 * Transform Prisma brand to frontend expected format (snake_case)
 */
function transformBrand(brand: any) {
  return {
    id: brand.id,
    brand_code: brand.brandCode,
    brand_name: brand.brandName,
    manufacturer: brand.manufacturer,
    website: brand.website,
    description: brand.description,
    logo_url: brand.logoUrl,
    is_active: brand.isActive,
    created_by: brand.createdBy,
    created_at: brand.createdAt,
    updated_at: brand.updatedAt,
  };
}

/**
 * GET /api/master-data/brands/:id
 * 
 * Fetch a single brand by ID
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
        { message: 'Invalid brand ID format' },
        { status: 400 },
      );
    }

    const brand = await prisma.brand.findUnique({
      where: { id },
    });

    if (!brand) {
      return NextResponse.json(
        { message: 'Brand not found' },
        { status: 404 },
      );
    }

    return NextResponse.json(transformBrand(brand));
  } catch (error) {
    console.error('Error fetching brand:', error);
    return NextResponse.json(
      { message: 'Oops! Something went wrong. Please try again in a moment.' },
      { status: 500 },
    );
  }
}

/**
 * PUT /api/master-data/brands/:id
 * 
 * Update a brand
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
        { message: 'Invalid brand ID format' },
        { status: 400 },
      );
    }

    const body = await request.json();

    const brand = await prisma.brand.update({
      where: { id },
      data: {
        brandCode: body.brand_code,
        brandName: body.brand_name,
        manufacturer: body.manufacturer || null,
        website: body.website || null,
        description: body.description || null,
        logoUrl: body.logo_url || null,
        isActive: body.is_active !== false,
      },
    });

    return NextResponse.json(transformBrand(brand));
  } catch (error) {
    console.error('Error updating brand:', error);
    return NextResponse.json(
      { message: 'Oops! Something went wrong. Please try again in a moment.' },
      { status: 500 },
    );
  }
}

/**
 * DELETE /api/master-data/brands/:id
 * 
 * Delete (soft delete) a brand by setting isActive to false
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
        { message: 'Invalid brand ID format' },
        { status: 400 },
      );
    }

    // Brands don't support soft delete, so we deactivate instead
    await prisma.brand.update({
      where: { id },
      data: {
        isActive: false,
      },
    });

    return NextResponse.json({ message: 'Brand deactivated successfully' });
  } catch (error) {
    console.error('Error deleting brand:', error);
    return NextResponse.json(
      { message: 'Oops! Something went wrong. Please try again in a moment.' },
      { status: 500 },
    );
  }
}

import { NextRequest, NextResponse } from 'next/server';
import { getServerSession } from 'next-auth/next';
import { prisma } from '@/lib/prisma';
import authOptions from '@/app/api/auth/[...nextauth]/auth-options';

/**
 * Transform Prisma category to frontend expected format (snake_case)
 */
function transformCategory(category: any) {
  return {
    id: category.id,
    category_code: category.categoryCode,
    category_name: category.categoryName,
    description: category.description,
    parent_category_id: category.parentCategoryId,
    is_active: category.isActive,
    display_order: category.displayOrder,
    created_by: category.createdBy,
    created_at: category.createdAt,
    updated_at: category.updatedAt,
    parent: category.parent ? {
      id: category.parent.id,
      category_code: category.parent.categoryCode,
      category_name: category.parent.categoryName,
    } : undefined,
    children: category.children?.map((child: any) => ({
      id: child.id,
      category_code: child.categoryCode,
      category_name: child.categoryName,
    })) || [],
  };
}

/**
 * GET /api/master-data/product-categories/:id
 * 
 * Fetch a single category by ID
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
        { message: 'Invalid category ID format' },
        { status: 400 },
      );
    }

    const category = await prisma.productCategory.findUnique({
      where: { id },
      include: {
        parent: true,
        children: true,
      },
    });

    if (!category) {
      return NextResponse.json(
        { message: 'Category not found' },
        { status: 404 },
      );
    }

    return NextResponse.json(transformCategory(category));
  } catch (error) {
    console.error('Error fetching category:', error);
    return NextResponse.json(
      { message: 'Oops! Something went wrong. Please try again in a moment.' },
      { status: 500 },
    );
  }
}

/**
 * PUT /api/master-data/product-categories/:id
 * 
 * Update a category
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
        { message: 'Invalid category ID format' },
        { status: 400 },
      );
    }

    const body = await request.json();

    const category = await prisma.productCategory.update({
      where: { id },
      data: {
        categoryCode: body.category_code,
        categoryName: body.category_name,
        description: body.description || null,
        parentCategoryId: body.parent_category_id || null,
        isActive: body.is_active !== false,
        displayOrder: body.display_order || null,
      },
      include: {
        parent: true,
        children: true,
      },
    });

    return NextResponse.json(transformCategory(category));
  } catch (error) {
    console.error('Error updating category:', error);
    return NextResponse.json(
      { message: 'Oops! Something went wrong. Please try again in a moment.' },
      { status: 500 },
    );
  }
}

/**
 * DELETE /api/master-data/product-categories/:id
 * 
 * Delete (soft delete) a category by setting isActive to false
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
        { message: 'Invalid category ID format' },
        { status: 400 },
      );
    }

    // Categories don't support soft delete, so we deactivate instead
    await prisma.productCategory.update({
      where: { id },
      data: {
        isActive: false,
      },
    });

    return NextResponse.json({ message: 'Category deactivated successfully' });
  } catch (error) {
    console.error('Error deleting category:', error);
    return NextResponse.json(
      { message: 'Oops! Something went wrong. Please try again in a moment.' },
      { status: 500 },
    );
  }
}

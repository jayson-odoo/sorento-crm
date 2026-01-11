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

    const categories = await prisma.productCategory.findMany({
      where: {
        isActive: true,
      },
      orderBy: {
        displayOrder: 'asc',
      },
    });

    // Transform to snake_case for frontend
    const transformedCategories = categories.map((cat) => ({
      id: cat.id,
      category_code: cat.categoryCode,
      category_name: cat.categoryName,
      description: cat.description,
      parent_category_id: cat.parentCategoryId,
      is_active: cat.isActive,
      display_order: cat.displayOrder,
      created_by: cat.createdBy,
      created_at: cat.createdAt,
      updated_at: cat.updatedAt,
    }));

    return NextResponse.json(transformedCategories);
  } catch (error) {
    console.error('Error fetching categories:', error);
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

    const category = await prisma.productCategory.create({
      data: {
        categoryCode: body.category_code,
        categoryName: body.category_name,
        description: body.description || null,
        parentCategoryId: body.parent_category_id || null,
        isActive: body.is_active !== false,
        displayOrder: body.display_order || 0,
        createdBy: session.user?.id || null,
      },
    });

    return NextResponse.json(category, { status: 201 });
  } catch (error) {
    console.error('Error creating category:', error);
    return NextResponse.json(
      { message: 'Oops! Something went wrong. Please try again in a moment.' },
      { status: 500 },
    );
  }
}

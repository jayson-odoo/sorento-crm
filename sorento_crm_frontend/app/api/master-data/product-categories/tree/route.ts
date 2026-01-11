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
      include: {
        parent: true,
        children: true,
      },
    });

    // Transform to snake_case for frontend and build tree structure
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
      parent: cat.parent ? {
        id: cat.parent.id,
        category_code: cat.parent.categoryCode,
        category_name: cat.parent.categoryName,
      } : undefined,
      children: cat.children?.map((child) => ({
        id: child.id,
        category_code: child.categoryCode,
        category_name: child.categoryName,
      })) || [],
    }));

    return NextResponse.json(transformedCategories);
  } catch (error) {
    console.error('Error fetching categories tree:', error);
    return NextResponse.json(
      { message: 'Oops! Something went wrong. Please try again in a moment.' },
      { status: 500 },
    );
  }
}

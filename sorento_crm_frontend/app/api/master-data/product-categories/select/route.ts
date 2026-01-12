import { NextResponse } from 'next/server';
import { getServerSession } from 'next-auth/next';
import { prisma } from '@/lib/prisma';
import authOptions from '@/app/api/auth/[...nextauth]/auth-options';

/**
 * GET /api/master-data/product-categories/select
 * 
 * Fetch categories for dropdown/select components
 */
export async function GET() {
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
      select: {
        id: true,
        categoryCode: true,
        categoryName: true,
        parentCategoryId: true,
      },
      orderBy: {
        categoryName: 'asc',
      },
    });

    // Transform to snake_case for consistency with other API endpoints
    const transformedCategories = categories.map((cat) => ({
      id: cat.id,
      category_code: cat.categoryCode,
      category_name: cat.categoryName,
      parent_category_id: cat.parentCategoryId,
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

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

    const categories = await (prisma as any).complaintCategory.findMany({
      where: {
        isActive: true,
      },
      orderBy: {
        categoryName: 'asc',
      },
    });

    // Transform to snake_case for frontend
    const transformedCategories = categories.map((category: any) => ({
      id: category.id,
      category_code: category.categoryCode,
      category_name: category.categoryName,
      description: category.description,
      severity: category.severity,
    }));

    return NextResponse.json({ data: transformedCategories });
  } catch (error) {
    console.error('Error fetching complaint categories:', error);
    return NextResponse.json(
      { message: 'Oops! Something went wrong. Please try again in a moment.' },
      { status: 500 },
    );
  }
}

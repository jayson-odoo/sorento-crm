import { NextResponse } from 'next/server';
import { getServerSession } from 'next-auth/next';
import { prisma } from '@/lib/prisma';
import authOptions from '@/app/api/auth/[...nextauth]/auth-options';

/**
 * GET /api/master-data/brands/select
 * 
 * Fetch brands for dropdown/select components
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

    const brands = await prisma.brand.findMany({
      where: {
        isActive: true,
      },
      select: {
        id: true,
        brandCode: true,
        brandName: true,
      },
      orderBy: {
        brandName: 'asc',
      },
    });

    // Transform to snake_case for consistency with other API endpoints
    const transformedBrands = brands.map((brand: { id: string; brandCode: string; brandName: string }) => ({
      id: brand.id,
      brand_code: brand.brandCode,
      brand_name: brand.brandName,
    }));

    return NextResponse.json(transformedBrands);
  } catch (error) {
    console.error('Error fetching brands:', error);
    return NextResponse.json(
      { message: 'Oops! Something went wrong. Please try again in a moment.' },
      { status: 500 },
    );
  }
}

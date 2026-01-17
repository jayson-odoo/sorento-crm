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
    const query = searchParams.get('query') || '';
    const sortField = searchParams.get('sort') || 'created_at';
    const sortDirection = searchParams.get('dir') === 'desc' ? 'desc' : 'asc';

    const whereClause: any = {
      ...(query ? {
        OR: [
          { brandCode: { contains: query, mode: 'insensitive' } },
          { brandName: { contains: query, mode: 'insensitive' } },
        ],
      } : {}),
    };

    const sortMap: Record<string, any> = {
      'created_at': 'createdAt',
      'brand_code': 'brandCode',
      'brand_name': 'brandName',
    };
    const mappedSortField = sortMap[sortField] || 'createdAt';

    const totalCount = await prisma.brand.count({ where: whereClause });

    const brands = await prisma.brand.findMany({
      where: whereClause,
      skip: (page - 1) * limit,
      take: limit,
      orderBy: { [mappedSortField]: sortDirection },
    });

    // Transform to snake_case for frontend
    const transformedBrands = brands.map((brand: { id: string; brandCode: string; brandName: string; manufacturer: string | null; website: string | null; description: string | null; logoUrl: string | null; isActive: boolean; createdAt: Date; updatedAt: Date | null; createdBy: string | null }) => ({
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
    }));

    return NextResponse.json({
      data: transformedBrands,
      pagination: {
        total: totalCount,
        page,
        limit,
      },
      empty: totalCount === 0,
    });
  } catch (error) {
    console.error('Error fetching brands:', error);
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

    const brand = await prisma.brand.create({
      data: {
        brandCode: body.brand_code,
        brandName: body.brand_name,
        manufacturer: body.manufacturer || null,
        website: body.website || null,
        description: body.description || null,
        logoUrl: body.logo_url || null,
        isActive: body.is_active !== false,
        createdBy: session.user?.id || null,
      },
    });

    return NextResponse.json(brand, { status: 201 });
  } catch (error) {
    console.error('Error creating brand:', error);
    return NextResponse.json(
      { message: 'Oops! Something went wrong. Please try again in a moment.' },
      { status: 500 },
    );
  }
}

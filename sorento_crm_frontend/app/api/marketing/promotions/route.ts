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

    const totalCount = await prisma.promotion.count();

    const promotions = await prisma.promotion.findMany({
      skip: (page - 1) * limit,
      take: limit,
      include: {
        _count: {
          select: {
            promotionProducts: true,
          },
        },
      },
      orderBy: {
        createdAt: 'desc',
      },
    });

    // Transform to snake_case for frontend
    const transformedPromotions = promotions.map((p: { id: string; promoCode: string; name: string; promoType: string; description: string | null; startDate: Date; endDate: Date; isActive: boolean; createdAt: Date; updatedAt: Date; createdBy: string | null; _count?: { promotionProducts: number } }) => ({
      id: p.id,
      promo_code: p.promoCode,
      name: p.name,
      promo_type: p.promoType,
      description: p.description,
      start_date: p.startDate,
      end_date: p.endDate,
      is_active: p.isActive,
      created_by: p.createdBy,
      created_at: p.createdAt,
      updated_at: p.updatedAt,
      products_count: p._count?.promotionProducts || 0,
    }));

    return NextResponse.json({
      data: transformedPromotions,
      pagination: {
        total: totalCount,
        page,
        limit,
      },
      empty: totalCount === 0,
    });
  } catch (error) {
    console.error('Error fetching promotions:', error);
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

    const promotion = await prisma.promotion.create({
      data: {
        promoCode: body.promo_code,
        name: body.name,
        promoType: body.promo_type,
        description: body.description || null,
        startDate: new Date(body.start_date),
        endDate: new Date(body.end_date),
        isActive: body.is_active !== false,
        createdBy: session.user?.id || null,
      },
    });

    // Transform to snake_case for frontend
    const transformedPromotion = {
      id: promotion.id,
      promo_code: promotion.promoCode,
      name: promotion.name,
      promo_type: promotion.promoType,
      description: promotion.description,
      start_date: promotion.startDate,
      end_date: promotion.endDate,
      is_active: promotion.isActive,
      created_by: promotion.createdBy,
      created_at: promotion.createdAt,
      updated_at: promotion.updatedAt,
    };

    return NextResponse.json(transformedPromotion, { status: 201 });
  } catch (error) {
    console.error('Error creating promotion:', error);
    return NextResponse.json(
      { message: 'Oops! Something went wrong. Please try again in a moment.' },
      { status: 500 },
    );
  }
}

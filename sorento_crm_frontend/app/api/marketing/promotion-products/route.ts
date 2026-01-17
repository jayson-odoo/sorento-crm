import { NextRequest, NextResponse } from 'next/server';
import { getServerSession } from 'next-auth/next';
import { prisma } from '@/lib/prisma';
import authOptions from '@/app/api/auth/[...nextauth]/auth-options';
import { Decimal } from '@prisma/client/runtime/library';

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
    const sortField = searchParams.get('sort') || 'createdAt';
    const sortDirection = searchParams.get('dir') === 'desc' ? 'desc' : 'asc';

    // Build where clause for search
    const whereClause: any = {};
    if (query) {
      whereClause.OR = [
        { promotion: { promoCode: { contains: query, mode: 'insensitive' } } },
        { promotion: { name: { contains: query, mode: 'insensitive' } } },
        { product: { productCode: { contains: query, mode: 'insensitive' } } },
        { product: { productName: { contains: query, mode: 'insensitive' } } },
      ];
    }

    const totalCount = await prisma.promotionProduct.count({ where: whereClause });

    // Map sort field to Prisma field
    const sortFieldMap: Record<string, string> = {
      'promotion.promo_code': 'promotion',
      'promotion.name': 'promotion',
      'product.product_code': 'product',
      'product.product_name': 'product',
      'created_at': 'createdAt',
    };

    const prismaSortField = sortFieldMap[sortField] || 'createdAt';
    const orderBy: any = {};
    
    if (prismaSortField === 'promotion') {
      orderBy.promotion = { promoCode: sortDirection };
    } else if (prismaSortField === 'product') {
      orderBy.product = { productCode: sortDirection };
    } else {
      orderBy[prismaSortField] = sortDirection;
    }

    const promotionProducts = await prisma.promotionProduct.findMany({
      where: whereClause,
      skip: (page - 1) * limit,
      take: limit,
      include: {
        promotion: {
          select: {
            id: true,
            promoCode: true,
            name: true,
            promoType: true,
            startDate: true,
            endDate: true,
            isActive: true,
          },
        },
        product: {
          select: {
            id: true,
            productCode: true,
            productName: true,
            listPrice: true,
            categoryId: true,
          },
        },
      },
      orderBy,
    });

    // Transform to snake_case for frontend and calculate discounts
    const transformedPromotionProducts = promotionProducts.map((pp: {
      id: string;
      promotionId: string;
      productId: string;
      createdAt: Date;
      updatedAt: Date | null;
      promotion: {
        id: string;
        promoCode: string;
        name: string;
        promoType: string;
        startDate: Date;
        endDate: Date;
        isActive: boolean;
      } | null;
      product: {
        id: string;
        productCode: string;
        productName: string;
        listPrice: Decimal;
        categoryId: string;
      } | null;
    }) => {
      const listPrice = pp.product?.listPrice ? Number(pp.product.listPrice) : 0;
      // Note: promotionPrice field doesn't exist in Prisma schema yet
      // Using listPrice as fallback until schema is updated
      const promoPrice = listPrice; // pp.promotionPrice || listPrice;
      const discountAmount = listPrice - promoPrice;
      const discountPercent = listPrice > 0 ? (discountAmount / listPrice) * 100 : 0;

      return {
        id: pp.id,
        promotion_id: pp.promotionId,
        product_id: pp.productId,
        promotion_price: null, // Will be added when schema is updated
        display_order: 0, // Not in schema, defaulting to 0
        created_at: pp.createdAt,
        updated_at: pp.updatedAt || null,
        promotion: pp.promotion ? {
          id: pp.promotion.id,
          promo_code: pp.promotion.promoCode,
          name: pp.promotion.name,
          promo_type: pp.promotion.promoType,
          start_date: pp.promotion.startDate,
          end_date: pp.promotion.endDate,
          is_active: pp.promotion.isActive,
        } : undefined,
        product: pp.product ? {
          id: pp.product.id,
          product_code: pp.product.productCode,
          product_name: pp.product.productName,
          list_price: listPrice,
          category_id: pp.product.categoryId,
        } : undefined,
        discount_amount: discountAmount,
        discount_percent: discountPercent,
      };
    });

    return NextResponse.json({
      data: transformedPromotionProducts,
      pagination: {
        total: totalCount,
        page,
        limit,
      },
      empty: totalCount === 0,
    });
  } catch (error) {
    console.error('Error fetching promotion products:', error);
    return NextResponse.json(
      { message: 'Oops! Something went wrong. Please try again in a moment.' },
      { status: 500 },
    );
  }
}

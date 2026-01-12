import { NextRequest, NextResponse } from 'next/server';
import { getServerSession } from 'next-auth/next';
import { prisma } from '@/lib/prisma';
import authOptions from '@/app/api/auth/[...nextauth]/auth-options';

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
        { message: 'Invalid promotion ID format' },
        { status: 400 },
      );
    }

    const promotion = await prisma.promotion.findUnique({
      where: { id },
      include: {
        promotionProducts: {
          include: {
            product: {
              include: {
                category: true,
              },
            },
          },
          orderBy: {
            createdAt: 'asc',
          },
        },
      },
    });

    if (!promotion) {
      return NextResponse.json(
        { message: 'Promotion not found' },
        { status: 404 },
      );
    }

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
      products: promotion.promotionProducts.map((pp) => ({
        id: pp.id,
        promotion_id: pp.promotionId,
        product_id: pp.productId,
        promotion_price: pp.promotionPrice ? Number(pp.promotionPrice) : null,
        promo_selling_price: pp.promotionPrice ? Number(pp.promotionPrice) : null,
        discount_amount: pp.discountAmount ? Number(pp.discountAmount) : null,
        discount_percent: pp.discountPercent ? Number(pp.discountPercent) : null,
        product: pp.product ? {
          id: pp.product.id,
          product_code: pp.product.productCode,
          product_name: pp.product.productName,
          list_price: Number(pp.product.listPrice),
          category: pp.product.category ? {
            id: pp.product.category.id,
            category_code: pp.product.category.categoryCode,
            category_name: pp.product.category.categoryName,
          } : undefined,
        } : undefined,
      })),
    };

    return NextResponse.json(transformedPromotion);
  } catch (error) {
    console.error('Error fetching promotion:', error);
    return NextResponse.json(
      { message: 'Oops! Something went wrong. Please try again in a moment.' },
      { status: 500 },
    );
  }
}

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
        { message: 'Invalid promotion ID format' },
        { status: 400 },
      );
    }

    const body = await request.json();

    const promotion = await prisma.promotion.update({
      where: { id },
      data: {
        promoCode: body.promo_code,
        name: body.name,
        promoType: body.promo_type,
        description: body.description || null,
        startDate: new Date(body.start_date),
        endDate: new Date(body.end_date),
        isActive: body.is_active !== false,
      },
      include: {
        promotionProducts: {
          include: {
            product: {
              include: {
                category: true,
              },
            },
          },
        },
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

    return NextResponse.json(transformedPromotion);
  } catch (error) {
    console.error('Error updating promotion:', error);
    return NextResponse.json(
      { message: 'Oops! Something went wrong. Please try again in a moment.' },
      { status: 500 },
    );
  }
}

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
        { message: 'Invalid promotion ID format' },
        { status: 400 },
      );
    }

    // Check if promotion exists
    const promotion = await prisma.promotion.findUnique({
      where: { id },
    });

    if (!promotion) {
      return NextResponse.json(
        { message: 'Promotion not found' },
        { status: 404 },
      );
    }

    // Permanently delete the promotion (cascade will delete promotion products)
    await prisma.promotion.delete({
      where: { id },
    });

    return NextResponse.json({ message: 'Promotion deleted successfully' });
  } catch (error) {
    console.error('Error deleting promotion:', error);
    
    // Handle foreign key constraint errors
    if (error instanceof Error && error.message.includes('Foreign key constraint')) {
      return NextResponse.json(
        { message: 'Cannot delete promotion. It is being used in other records.' },
        { status: 400 },
      );
    }

    return NextResponse.json(
      { message: 'Oops! Something went wrong. Please try again in a moment.' },
      { status: 500 },
    );
  }
}

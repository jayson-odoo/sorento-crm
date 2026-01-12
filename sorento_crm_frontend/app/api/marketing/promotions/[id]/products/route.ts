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

    const promotionProducts = await prisma.promotionProduct.findMany({
      where: { promotionId: id },
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
    });

    // Transform to snake_case for frontend
    const transformedProducts = promotionProducts.map((pp) => ({
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
    }));

    return NextResponse.json(transformedProducts);
  } catch (error) {
    console.error('Error fetching promotion products:', error);
    return NextResponse.json(
      { message: 'Oops! Something went wrong. Please try again in a moment.' },
      { status: 500 },
    );
  }
}

export async function POST(
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

    // Validate product_id
    if (!body.product_id || !uuidRegex.test(body.product_id)) {
      return NextResponse.json(
        { message: 'Invalid product ID format' },
        { status: 400 },
      );
    }

    // Calculate discount if promotion_price is provided
    const product = await prisma.product.findUnique({
      where: { id: body.product_id },
      select: { listPrice: true },
    });

    let promotionPrice = body.promotion_price ? Number(body.promotion_price) : null;
    let discountAmount = null;
    let discountPercent = null;

    if (promotionPrice && product) {
      const listPrice = Number(product.listPrice);
      discountAmount = listPrice - promotionPrice;
      discountPercent = listPrice > 0 ? (discountAmount / listPrice) * 100 : 0;
    }

    const promotionProduct = await prisma.promotionProduct.create({
      data: {
        promotionId: id,
        productId: body.product_id,
        promotionPrice: promotionPrice,
        discountAmount: discountAmount,
        discountPercent: discountPercent,
      },
      include: {
        product: {
          include: {
            category: true,
          },
        },
      },
    });

    // Transform to snake_case for frontend
    const transformedProduct = {
      id: promotionProduct.id,
      promotion_id: promotionProduct.promotionId,
      product_id: promotionProduct.productId,
      promotion_price: promotionProduct.promotionPrice ? Number(promotionProduct.promotionPrice) : null,
      promo_selling_price: promotionProduct.promotionPrice ? Number(promotionProduct.promotionPrice) : null,
      discount_amount: promotionProduct.discountAmount ? Number(promotionProduct.discountAmount) : null,
      discount_percent: promotionProduct.discountPercent ? Number(promotionProduct.discountPercent) : null,
      product: promotionProduct.product ? {
        id: promotionProduct.product.id,
        product_code: promotionProduct.product.productCode,
        product_name: promotionProduct.product.productName,
        list_price: Number(promotionProduct.product.listPrice),
        category: promotionProduct.product.category ? {
          id: promotionProduct.product.category.id,
          category_code: promotionProduct.product.category.categoryCode,
          category_name: promotionProduct.product.category.categoryName,
        } : undefined,
      } : undefined,
    };

    return NextResponse.json(transformedProduct, { status: 201 });
  } catch (error) {
    console.error('Error adding product to promotion:', error);
    
    // Handle unique constraint violation (product already in promotion)
    if (error instanceof Error && error.message.includes('Unique constraint')) {
      return NextResponse.json(
        { message: 'This product is already in the promotion' },
        { status: 400 },
      );
    }

    return NextResponse.json(
      { message: 'Oops! Something went wrong. Please try again in a moment.' },
      { status: 500 },
    );
  }
}

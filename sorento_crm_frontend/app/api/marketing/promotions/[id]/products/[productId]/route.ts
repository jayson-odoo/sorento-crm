import { NextRequest, NextResponse } from 'next/server';
import { getServerSession } from 'next-auth/next';
import { prisma } from '@/lib/prisma';
import authOptions from '@/app/api/auth/[...nextauth]/auth-options';

export async function PUT(
  request: NextRequest,
  { params }: { params: Promise<{ id: string; productId: string }> },
) {
  try {
    const session = await getServerSession(authOptions);

    if (!session) {
      return NextResponse.json(
        { message: 'Unauthorized request' },
        { status: 401 },
      );
    }

    const { id, productId } = await params;

    // Validate UUIDs
    const uuidRegex = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
    if (!uuidRegex.test(id) || !uuidRegex.test(productId)) {
      return NextResponse.json(
        { message: 'Invalid promotion or product ID format' },
        { status: 400 },
      );
    }

    const body = await request.json();

    // Get the product to calculate discount
    const product = await prisma.product.findUnique({
      where: { id: productId },
      select: { listPrice: true },
    });

    if (!product) {
      return NextResponse.json(
        { message: 'Product not found' },
        { status: 404 },
      );
    }

    let promotionPrice = body.promotion_price ? Number(body.promotion_price) : null;
    let discountAmount = null;
    let discountPercent = null;

    if (promotionPrice) {
      const listPrice = Number(product.listPrice);
      discountAmount = listPrice - promotionPrice;
      discountPercent = listPrice > 0 ? (discountAmount / listPrice) * 100 : 0;
    }

    const promotionProduct = await prisma.promotionProduct.update({
      where: {
        promotionId_productId: {
          promotionId: id,
          productId: productId,
        },
      },
      data: {
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

    return NextResponse.json(transformedProduct);
  } catch (error) {
    console.error('Error updating promotion product price:', error);
    return NextResponse.json(
      { message: 'Oops! Something went wrong. Please try again in a moment.' },
      { status: 500 },
    );
  }
}

export async function DELETE(
  request: NextRequest,
  { params }: { params: Promise<{ id: string; productId: string }> },
) {
  try {
    const session = await getServerSession(authOptions);

    if (!session) {
      return NextResponse.json(
        { message: 'Unauthorized request' },
        { status: 401 },
      );
    }

    const { id, productId } = await params;

    // Validate UUIDs
    const uuidRegex = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
    if (!uuidRegex.test(id) || !uuidRegex.test(productId)) {
      return NextResponse.json(
        { message: 'Invalid promotion or product ID format' },
        { status: 400 },
      );
    }

    // Check if promotion product exists
    const promotionProduct = await prisma.promotionProduct.findUnique({
      where: {
        promotionId_productId: {
          promotionId: id,
          productId: productId,
        },
      },
    });

    if (!promotionProduct) {
      return NextResponse.json(
        { message: 'Product not found in promotion' },
        { status: 404 },
      );
    }

    // Permanently delete the promotion product
    await prisma.promotionProduct.delete({
      where: {
        promotionId_productId: {
          promotionId: id,
          productId: productId,
        },
      },
    });

    return NextResponse.json({ message: 'Product removed from promotion successfully' });
  } catch (error) {
    console.error('Error removing product from promotion:', error);
    return NextResponse.json(
      { message: 'Oops! Something went wrong. Please try again in a moment.' },
      { status: 500 },
    );
  }
}

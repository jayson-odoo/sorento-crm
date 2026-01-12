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

    const totalCount = await prisma.stock.count();

    const stock = await prisma.stock.findMany({
      skip: (page - 1) * limit,
      take: limit,
      include: {
        product: {
          include: {
            category: true,
            baseUom: true,
          },
        },
        warehouse: true,
      },
    });

    // Transform Prisma response (camelCase) to frontend expected format (snake_case)
    const transformedStock = stock.map((item) => {
      // Calculate status based on quantity and reorder level
      // Use reorderPoint from stock if available, otherwise fall back to product reorderLevel
      const reorderLevel = item.reorderPoint ?? item.product?.reorderLevel ?? 0;
      const quantity = item.quantityOnHand;
      let status: 'low' | 'critical' | 'normal' | 'overstock' = 'normal';
      if (quantity < reorderLevel * 0.5) {
        status = 'critical';
      } else if (quantity < reorderLevel) {
        status = 'low';
      } else if (quantity > reorderLevel * 2) {
        status = 'overstock';
      }

      return {
        id: item.id,
        product_id: item.productId,
        warehouse_id: item.warehouseId,
        quantity: item.quantityOnHand,
        reserved_quantity: item.quantityReserved,
        uom_id: item.product?.baseUomId || '',
        created_at: item.createdAt,
        updated_at: item.updatedAt || item.createdAt,
        product: item.product ? {
          id: item.product.id,
          product_code: item.product.productCode,
          product_name: item.product.productName,
          reorder_level: item.reorderPoint ?? item.product.reorderLevel,
          category: item.product.category ? {
            category_name: item.product.category.categoryName,
          } : undefined,
        } : undefined,
        warehouse: item.warehouse ? {
          id: item.warehouse.id,
          warehouse_name: item.warehouse.warehouseName,
        } : undefined,
        available: item.quantityAvailable,
        status,
      };
    });

    return NextResponse.json({
      data: transformedStock,
      pagination: {
        total: totalCount,
        page,
        limit,
      },
      empty: totalCount === 0,
    });
  } catch (error) {
    console.error('Error fetching stock balance:', error);
    return NextResponse.json(
      { message: 'Oops! Something went wrong. Please try again in a moment.' },
      { status: 500 },
    );
  }
}

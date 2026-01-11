import { NextResponse } from 'next/server';
import { getServerSession } from 'next-auth/next';
import { prisma } from '@/lib/prisma';
import authOptions from '@/app/api/auth/[...nextauth]/auth-options';

export async function GET() {
  try {
    const session = await getServerSession(authOptions);

    if (!session) {
      return NextResponse.json(
        { message: 'Unauthorized request' },
        { status: 401 },
      );
    }

    // Count unique products in stock (stock table doesn't have quantity field)
    const totalSkus = await prisma.stock.groupBy({
      by: ['productId'],
    });

    // Stock table doesn't have quantity field - use stock_batches instead
    const totalQuantityResult = await prisma.stockBatch.aggregate({
      _sum: {
        quantity: true,
      },
    });

    // Low stock alerts would need to be calculated from stock_batches
    // For now, return empty array since stock table structure is different
    const lowStockAlerts: any[] = [];

    return NextResponse.json({
      total_skus: totalSkus.length,
      total_quantity: totalQuantityResult._sum.quantity || 0,
      low_stock_alert_count: 0,
      overstock_warning_count: 0,
      stock_by_warehouse: [],
      stock_by_category: [],
      stock_movement_30_days: [],
      low_stock_alerts: lowStockAlerts,
    });
  } catch (error) {
    console.error('Error fetching stock dashboard:', error);
    return NextResponse.json(
      { message: 'Oops! Something went wrong. Please try again in a moment.' },
      { status: 500 },
    );
  }
}
